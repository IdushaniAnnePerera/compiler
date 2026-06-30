"""
Phase 6: Target Code Generation  (Register-based machine model)

New additions
-------------
AddressDescriptor
    Tracks where each identifier's current value lives: in a register (Rn),
    in memory (mem), or both.  A variable starts in memory; when loaded into
    a register it is marked as being in both locations; when overwritten
    by a computation the old memory copy is stale.

Activation Record (AR) setup / teardown
    If a symbol table is supplied, the generator emits:
        AR_INIT <bytes>   — push activation record of <bytes> bytes on the
                            control stack  (SP = SP - bytes)
        FP_SET            — set the frame pointer to SP
        AR_RET            — pop the record on program exit  (SP = SP + bytes)
    This models the run-time environment described in Lecture 8: each procedure
    (here: the main program) owns an activation record on a control stack.

    The record layout matches the byte offsets stored in the symbol table
    (computed in Phase 3) so that LOAD/STORE offsets would be
    correct in a real machine implementation.

Instruction set (simple two-operand register machine)
------------------------------------------------------
  AR_INIT n     push n-byte activation record; SP = SP - n
  FP_SET        FP = SP  (frame pointer anchors the record)
  MOV  src, Rd  load constant or variable into register Rd
  ADD  Rs, Rd   Rd = Rd + Rs   (SUB, MUL, DIV likewise)
  CMPLT/...     Rd = (Rd ? Rs) -> 1 or 0
  AND/OR        logical on registers
  NEG/NOT       unary
  SHL  n, Rd    Rd = Rd << n   (strength-reduction replacement for *2^n)
  ALLOC name n  allocate array 'name' of n elements
  LOAD_ARR name, Ri, Rd   Rd = name[Ri]
  STORE_ARR name, Ri, Rs  name[Ri] = Rs
  LABEL Ln
  JMP  Ln       unconditional jump
  JZ   Rs, Ln   jump if Rs == 0
  PRINT Rs
  AR_RET        pop activation record; SP = SP + n
"""

from ir_gen import Quad

ARITH = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV"}
REL   = {"<": "CMPLT", ">": "CMPGT", "<=": "CMPLE",
          ">=": "CMPGE", "==": "CMPEQ", "!=": "CMPNE"}
LOGIC = {"&&": "AND", "||": "OR"}


# ── Address Descriptor ────────────────────────────────────────────────────────

class AddressDescriptor:
    """
    Tracks where each identifier's current value lives.

    Locations are stored as strings:
        "mem"  — value is in memory (the activation record)
        "Rn"   — value is in register Rn

    A value may live in multiple locations simultaneously (e.g. after a load,
    the variable is in both its memory slot and the scratch register).
    """

    def __init__(self):
        self._locs = {}    # name -> set of location strings

    def mark_in_reg(self, name, reg):
        self._locs.setdefault(name, set()).add(reg)

    def mark_in_mem(self, name):
        self._locs.setdefault(name, set()).add("mem")

    def evict_reg(self, reg):
        """Remove `reg` from all descriptors (register is being reused)."""
        for locs in self._locs.values():
            locs.discard(reg)

    def has_reg(self, name):
        return any(v != "mem" for v in self._locs.get(name, set()))

    def get_reg(self, name):
        for v in self._locs.get(name, set()):
            if v != "mem":
                return v
        return None

    def locations(self, name):
        return frozenset(self._locs.get(name, set()))

    def dump(self):
        """Return a sorted dict  name -> sorted list of locations."""
        result = {}
        for name, locs in sorted(self._locs.items()):
            if locs:
                result[name] = sorted(locs)
        return result


# ── Register Allocator ────────────────────────────────────────────────────────

class RegisterAllocator:
    """
    Simple sequential register allocator.
    TAC temporaries (t1, t2, ...) are assigned registers R1, R2, ... in order.
    Variables keep their symbolic names and are loaded/stored via MOV.
    """

    def __init__(self):
        self.reg_of = {}
        self.count  = 0

    def reg(self, name):
        if isinstance(name, str) and name.startswith("R"):
            return name
        if name not in self.reg_of:
            self.count += 1
            self.reg_of[name] = f"R{self.count}"
        return self.reg_of[name]


def _is_temp(v):
    return isinstance(v, str) and (v.startswith("t") or v.startswith("tP"))


# ── Target Code Generator ─────────────────────────────────────────────────────

def generate_target(code, sym_table=None):
    """
    Translate optimized TAC into assembly instructions.

    Parameters
    ----------
    code       : list of Quad  (optimized TAC from Phase 5)
    sym_table  : optional symbol table (HashTable of name -> SymbolEntry)
                 When provided:
                   - variables are pre-marked as being in memory
                   - AR_INIT / FP_SET / AR_RET instructions are emitted
                   - the AR size is the sum of all entry sizes

    Returns
    -------
    (asm, ad_dump)
        asm     : list of assembly instruction strings
        ad_dump : dict name -> [locations]  (final address descriptor state)
    """
    asm = []
    ra  = RegisterAllocator()
    ad  = AddressDescriptor()

    # ── Activation Record setup ───────────────────────────────────────────────
    if sym_table is not None:
        total_bytes = sum(entry.size for _, entry in sym_table.items())
        for name, _ in sym_table.items():
            ad.mark_in_mem(name)
        if total_bytes > 0:
            asm.append(f"AR_INIT {total_bytes:<6}; push {total_bytes}-byte activation record  (SP = SP - {total_bytes})")
            asm.append(f"FP_SET         ; frame pointer = SP  (anchors activation record)")

    # ── Helper: load an operand into a register ───────────────────────────────
    def load(operand):
        """Return a register holding operand, emitting MOV if it is a variable."""
        if _is_temp(operand):
            r = ra.reg(operand)
            ad.mark_in_reg(operand, r)
            return r
        # Variable or constant: load into a fresh scratch register
        rd = ra.reg(f"_acc{len(asm)}")
        asm.append(f"MOV {operand}, {rd}")
        if isinstance(operand, str) and not _is_const_val(operand):
            ad.mark_in_reg(operand, rd)   # variable now also in this register
            ad.mark_in_mem(operand)       # (still in memory too)
        return rd

    def _is_const_val(v):
        if isinstance(v, str) and (v.startswith('"') or v in ("true", "false")):
            return True  # string literal or boolean literal
        try:
            float(str(v)); return True
        except (ValueError, TypeError):
            return False

    # ── Main code-generation loop ─────────────────────────────────────────────
    for q in code:

        if q.op in ARITH:
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            r2 = load(q.arg2)
            asm.append(f"{ARITH[q.op]} {r2}, {rd}")
            ad.mark_in_reg(q.result, rd)

        elif q.op in REL:
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            r2 = load(q.arg2)
            asm.append(f"{REL[q.op]} {r2}, {rd}")
            ad.mark_in_reg(q.result, rd)

        elif q.op in LOGIC:
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            r2 = load(q.arg2)
            asm.append(f"{LOGIC[q.op]} {r2}, {rd}")
            ad.mark_in_reg(q.result, rd)

        elif q.op == "shl":
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            asm.append(f"SHL {q.arg2}, {rd}")
            ad.mark_in_reg(q.result, rd)

        elif q.op == "uminus":
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            asm.append(f"NEG {rd}")
            ad.mark_in_reg(q.result, rd)

        elif q.op == "not":
            rd = ra.reg(q.result)
            r1 = load(q.arg1)
            asm.append(f"MOV {r1}, {rd}")
            asm.append(f"NOT {rd}")
            ad.mark_in_reg(q.result, rd)

        elif q.op == "=":
            rs = load(q.arg1)
            if _is_temp(q.result):
                rd = ra.reg(q.result)
                asm.append(f"MOV {rs}, {rd}")
                ad.mark_in_reg(q.result, rd)
            else:
                asm.append(f"MOV {rs}, {q.result}")
                ad.mark_in_mem(q.result)   # written back to memory slot

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
            asm.append(f"ALLOC {q.arg1}, {q.arg2}")
            ad.mark_in_mem(q.arg1)

        elif q.op == "load_arr":
            rd    = ra.reg(q.result)
            r_idx = load(q.arg2)
            asm.append(f"LOAD_ARR {q.arg1}, {r_idx}, {rd}")
            ad.mark_in_reg(q.result, rd)

        elif q.op == "store_arr":
            r_idx = load(q.arg2)
            r_val = load(q.result)
            asm.append(f"STORE_ARR {q.arg1}, {r_idx}, {r_val}")
            ad.mark_in_mem(q.arg1)   # array contents updated in memory

    # ── Activation Record teardown ────────────────────────────────────────────
    if sym_table is not None and total_bytes > 0:
        asm.append(f"AR_RET         ; pop activation record  (SP = SP + {total_bytes})")

    return asm, ad.dump()
