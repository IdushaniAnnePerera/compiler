"""
Phase 6: Target Code Generation  (Register-based machine model)

This matches the model taught in Lecture 7, where three-address temporaries
r1, r2, ... are mapped onto target registers and the code generator assumes
a supply of registers (R1, R2, ...).

Instruction set (simple two-operand register machine):
  MOV  src, Rd       load a constant or variable into register Rd
  MOV  Rs, dst       store register Rs into a variable
  ADD  Rs, Rd        Rd = Rd + Rs   (likewise SUB, MUL, DIV)
  CMPLT/CMPGT/...    Rd = (Rd ? Rs)  -> 1 or 0  for relational operators
  AND/OR             logical on registers
  NEG  Rd            Rd = -Rd
  NOT  Rd            Rd = !Rd
  LABEL Ln
  JMP  Ln            unconditional jump
  JZ   Rs, Ln        jump to Ln if Rs == 0 (false)
  PRINT Rs           output register Rs
"""

from ir_gen import Quad

ARITH = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV"}
REL = {"<": "CMPLT", ">": "CMPGT", "<=": "CMPLE",
       ">=": "CMPGE", "==": "CMPEQ", "!=": "CMPNE"}
LOGIC = {"&&": "AND", "||": "OR"}


class RegisterAllocator:
    """Maps TAC temporaries/vars to registers. Temporaries (t1, t2, ...)
    get registers R1, R2, ...; ordinary variables keep their own names
    and are loaded/stored via MOV."""

    def __init__(self):
        self.reg_of = {}
        self.count = 0

    def reg(self, name):
        # already a register
        if isinstance(name, str) and name.startswith("R"):
            return name
        if name not in self.reg_of:
            self.count += 1
            self.reg_of[name] = f"R{self.count}"
        return self.reg_of[name]


def _is_temp(v):
    return isinstance(v, str) and v.startswith("t")


def generate_target(code):
    asm = []
    ra = RegisterAllocator()

    def load(operand):
        """Return a register holding `operand`, emitting a MOV if needed."""
        if _is_temp(operand):
            return ra.reg(operand)             # temp already lives in a register
        rd = ra.reg("_acc" + str(len(asm)))    # fresh scratch register
        asm.append(f"MOV {operand}, {rd}")
        return rd

    for q in code:
        if q.op in ARITH:
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            r2 = load(q.arg2)
            asm.append(f"{ARITH[q.op]} {r2}, {rd}")
        elif q.op in REL:
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            r2 = load(q.arg2)
            asm.append(f"{REL[q.op]} {r2}, {rd}")
        elif q.op in LOGIC:
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            r2 = load(q.arg2)
            asm.append(f"{LOGIC[q.op]} {r2}, {rd}")
        elif q.op == "shl":
            # Strength-reduced left-shift: result = arg1 << arg2 (literal count)
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            asm.append(f"SHL {q.arg2}, {rd}")
        elif q.op == "uminus":
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            asm.append(f"NEG {rd}")
        elif q.op == "not":
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            asm.append(f"NOT {rd}")
        elif q.op == "=":
            # result = arg1
            # If the destination is a temp it lives in a register; otherwise store to variable.
            rs = load(q.arg1)
            if _is_temp(q.result):
                rd = ra.reg(q.result)
                asm.append(f"MOV {rs}, {rd}")
            else:
                asm.append(f"MOV {rs}, {q.result}")
        elif q.op == "label":
            asm.append(f"LABEL {q.result}")
        elif q.op == "goto":
            asm.append(f"JMP {q.result}")
        elif q.op == "ifFalse":
            rs = load(q.arg1)
            asm.append(f"JZ {rs}, {q.result}")
        elif q.op == "print":
            rs = load(q.arg1)
            asm.append(f"PRINT {rs}")
        elif q.op == "alloc_arr":
            # q.arg1 = array name, q.arg2 = size
            asm.append(f"ALLOC {q.arg1}, {q.arg2}")
        elif q.op == "load_arr":
            # t = arr[idx]  — q.arg1=arr, q.arg2=idx, q.result=dest_temp
            rd    = ra.reg(q.result)
            r_idx = load(q.arg2)
            asm.append(f"LOAD_ARR {q.arg1}, {r_idx}, {rd}")
        elif q.op == "store_arr":
            # arr[idx] = val  — q.arg1=arr, q.arg2=idx, q.result=val_place
            r_idx = load(q.arg2)
            r_val = load(q.result)
            asm.append(f"STORE_ARR {q.arg1}, {r_idx}, {r_val}")
    return asm
