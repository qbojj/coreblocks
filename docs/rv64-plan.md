# RV64 Support Plan for Coreblocks

This document describes the work required to add RV64 support to the Coreblocks CPU.
It is based on the current codebase state and is intended as an implementation roadmap, not a specification.

Cross-checked against the RISC-V Unprivileged ISA manual in this repo (`riscv-isa-manual/modules/unpriv/pages/rv64.adoc`, `rv-32-64g.adoc`, `m-st-ext.adoc`, `b-st-ext.adoc`, `zalrsc.adoc`) and `riscv-arch-test/tests/env/encoding.h`.

---

## 0. ISA Spec Cross-Check (2025-06)

### Verified correct in the plan

- **RV64-only instruction list** for I/M/A matches the opcode tables in `rv-32-64g.adoc` (§ RV64I, RV64M, RV64A).
- **W-type semantics**: all `*w` / `*iw` ops ignore upper 32 bits of inputs and **sign-extend** the 32-bit result to XLEN (`rv64.adoc`, `norm:rv64_w_sex`).
- **MULW / DIVW / DIVUW / REMW / REMUW** encodings use `OP-32` (`0111010`) with the same funct3/funct7 pattern as RV32M ops on `OP` (`rv-32-64g.adoc`).
- **LD / SD** use `funct3=D` (011); **LWU** uses `funct3=110` on `LOAD` (`norm:lwu_enc`).
- **64-bit atomics** use `funct3=D` (011); same funct5 as `.w` variants (`RV64A` table in `rv-32-64g.adoc`).
- **Zba RV64-only ops**: `add.uw`, `sh{1,2,3}add.uw`, `slli.uw` (`b-st-ext.adoc`).
- **Zbb RV64-only ops**: `clzw`, `ctzw`, `cpopw`, `rolw`, `rorw`, `roriw`; **REV8** has distinct RV32 vs RV64 encodings (`Funct12.REV8_32` vs `REV8_64` in `isa_consts.py`).
- **SLLI/SRLI/SRAI** on RV64 use **6-bit** shamt in `instr[25:20]`; **SLL/SRL/SRA** use `rs2[5:0]` (`norm:sll_srl_sra_sh_amt_rv64i`).

### Corrections applied after spec review

| Topic | Original plan | Spec-correct behavior |
|-------|---------------|----------------------|
| **LD** | Described as zero-extending | Loads a **full 64-bit** value into `rd` (`norm:ld_op_rv64i`) |
| **LW** (existing opcode) | Not called out | On RV64, **sign-extends** 32-bit load to 64 bits (`norm:lw_op_rv64i`); LSU must do this |
| **LWU funct3** | “110 (OR alias)” | Encoding is `LOAD` + `funct3=110`; use `Funct3` enum value, not the overloaded name |
| **SLLIW/SRLIW/SRAIW** with `imm[5]≠0` | “illegal” | **Reserved** encodings (need not trap; may treat as illegal in core) |
| **SLLW/SRLW/SRAW** | Not specified | Shift amount is **`rs2[4:0]`** only (`rv64.adoc`) |
| **REMUW** | Implied unsigned remainder | Result is still **sign-extended to 64 bits**, including on divide-by-zero (`norm:remw_remuw_result_sign`, `m-st-ext.adoc`) |
| **LR.W / SC.W on RV64** | Not mentioned | Still available; **sign-extend** value loaded into `rd` (`zalrsc.adoc`) |
| **Zbkb (`pack*`, `brev8`)** | Listed as required for `full` | **Not in current `full` config** (only Zba/Zbb/Zbs from `B`); needed only if Zbkb is added |

### Gaps found in spec review (missing from original plan)

1. **LUI / AUIPC on RV64** (`rv64.adoc`): both form a **32-bit** result (U-immediate in bits `[31:12]`, low 12 zero), then **sign-extend to 64 bits**. The current decoder places the 20-bit U-field at `instr[31:12] << (xlen - 20)`, which on RV64 puts it at bits `[63:44]` instead of `[31:12]`. **Must fix before RV64 bring-up.**

2. **ADDIW with imm=0** is defined as sign-extension of low 32 bits of `rs1` (pseudoinstruction `sext.w`).

3. **Existing 32-bit loads/stores on RV64** (`lb/lh/lw/lbu/lhu`, `sb/sh/sw`) retain RV32 semantics but with XLEN-wide results for loads (`rv64.adoc` § Load and Store). Verify LSU postprocessing for `LW` sign-extension at XLEN=64.

### Spec references (primary)

| Topic | Manual location |
|-------|-----------------|
| RV64I W-ops, shifts, loads | `riscv-isa-manual/modules/unpriv/pages/rv64.adoc` |
| Opcode/funct tables | `riscv-isa-manual/modules/unpriv/pages/rv-32-64g.adoc` |
| MULW, DIVW, REMW | `riscv-isa-manual/modules/unpriv/pages/m-st-ext.adoc` |
| LR.D, SC.D, AMO.D | `rv-32-64g.adoc` + `riscv-isa-manual/src/unpriv/zalrsc.adoc` |
| Zba/Zbb/Zbkb | `riscv-isa-manual/modules/unpriv/pages/b-st-ext.adoc` |
| Encodings (masks) | `coreblocks/test/external/riscv-arch-test/riscv-arch-test/tests/env/encoding.h` |

---

## 1. Current State Summary

### What already scales with `xlen`

| Area | Status |
|------|--------|
| `CoreConfiguration.xlen` | Parameter exists, default `32` (`coreblocks/params/core_configuration.py`) |
| `ISA` parsing | Accepts `rv32` / `rv64` / `rv128`; sets `xlen`, MISA MXL field (`coreblocks/arch/isa.py`) |
| `GenParams` | Bus `data_width = xlen`, phys addr defaults to **56 bits on RV64** (`coreblocks/params/genparams.py`) |
| Register file, ROB, most pipeline signals | Width = `gen_params.isa.xlen` |
| Branches / jumps / compares | Use full XLEN (should work once decoded) |
| Base `add`/`sub`/logic on XLEN | Already 64-bit-wide if `xlen=64` |
| CSR block | RV64 `mstatus` fields (UXL/SXL/SBE/MBE), RV64 PMP layout, single 64-bit CSR shadows (`coreblocks/priv/csr/csr_instances.py`) |
| MMU infrastructure | `SatpMode` SV39/48/57 defined; RV64 PTE layout in walker; TLB/translation parameterized |
| I-cache bus addressing | Uses `word_width_bytes`, not hardcoded (`coreblocks/cache/icache.py`) |
| Compressed decoder | RV64 expansions partially written (`coreblocks/frontend/decoder/rvc.py`); unit tests exist for `rv64ic` |

### What is RV32-only today

| Area | Gap |
|------|-----|
| Instruction encodings | No RV64-only opcodes in `instructions_by_optype` |
| Decoder | No `OP_IMM_32` / `OP32` handling; shift immediates use 5 bits only |
| M extension | `MULW` stubbed/commented (`coreblocks/func_blocks/fu/mul_unit.py`) |
| D extension (divide) | No `*W` variants |
| Shift / ALU | No `*W` ops; no RV64 Zba/Zbb variants; LUI/AUIPC immediate wrong for RV64 |
| LSU | No `ld`/`sd`/`lwu`; bus addr uses `paddr >> 2` (32-bit word assumption) |
| Atomics | Only `funct3=W` (`instr_description.py`) |
| Tests / CI | All regression builds target RV32; synthesis benchmarks RV32 only |
| Preset configs | `basic`, `full`, etc. all emit `rv32…` ISA strings |

---

## 2. Target ISA Scope

For parity with the existing **`full`** RV32 configuration, the RV64 target is roughly:

```
rv64imac_zicond_zicsr_zifencei_zcb_zba_zbb_zbc_zbkx_zbs_u_s
```

(with supervisor + user mode, atomics, bitmanip — matching current extension set).

**Out of scope for initial RV64 bring-up** (not implemented for RV32 either): F/D/Q/V, hypervisor, Zicbo*, Svnapot beyond what arch-tests require later, **Zbkb** (`pack*`, `brev8` — not in current `full` config; add only if Zbkb is enabled).

---

## 3. Missing Instructions (Exact List)

RV64 adds instructions in four categories: **new loads/stores**, **32-bit word ops (W-type)**, **64-bit-only B-extension ops**, and **64-bit atomics**.

### 3.1 RV64I — loads & stores (3 new)

| Instruction | Opcode | funct3 | Notes |
|-------------|--------|--------|-------|
| **LD** | `LOAD` | `D` (011) | 8-byte load into `rd` (full 64-bit value) |
| **LWU** | `LOAD` | `110` | Zero-extend 32→64 |
| **SD** | `STORE` | `D` (011) | 8-byte store (low 64 bits of `rs2`) |

Existing `lb/lh/lbu/lhu` behave as on RV32 (with XLEN-wide `rd`). **`LW` on RV64 sign-extends** the 32-bit value (spec change vs RV32 width). LSU must handle 64-bit bus width, 8-byte alignment for `LD`/`SD`, and correct extension for `LW`/`LWU`.

**`riscv-tests` coverage:** `rv64ui/{ld,lwu,sd,ld_st,st_ld}.S`

### 3.2 RV64I — 32-bit word operations (OP-IMM-32 / OP-32)

All W-type results must be **sign-extended to 64 bits** (bits `[63:32]` = bit 31).

#### OP-IMM-32 (`opcode = 0011010`)

| Instruction | funct3 | funct7/imm | Shift amount |
|-------------|--------|------------|--------------|
| **ADDIW** | ADD (000) | imm[11:0] | — |
| **SLLIW** | SLL (001) | shamt[4:0], bit 25 = 0 | 5 bits |
| **SRLIW** | SR (101) | shamt[4:0], funct7=0000000 | 5 bits |
| **SRAIW** | SR (101) | shamt[4:0], funct7=0100000 | 5 bits; `imm[5]≠0` reserved |

Register-register W shifts (**SLLW/SRLW/SRAW**) use shift amount **`rs2[4:0]`** only.

#### OP-32 (`opcode = 0111010`)

| Instruction | funct3 | funct7 |
|-------------|--------|--------|
| **ADDW** | ADD (000) | 0000000 |
| **SUBW** | ADD (000) | 0100000 |
| **SLLW** | SLL (001) | 0000000 |
| **SRLW** | SR (101) | 0000000 |
| **SRAW** | SR (101) | 0100000 |

**`riscv-tests` coverage:** `rv64ui/{addiw,addw,subw,slliw,sllw,srliw,srlw,sraiw,sraw}.S`

### 3.3 RV64I — 64-bit shift immediate fix (not new opcodes)

Existing `SLLI`/`SRLI`/`SRAI` on RV64 use **6-bit** shamt (`instr[25:20]`), not 5.

Decoder currently does:

```python
with m.If((opcode == Opcode.OP_IMM) & ((self.funct3 == Funct3.SLL) | (self.funct3 == Funct3.SR))):
    m.d.comb += iimm12.eq(instr[20:25])
```

This must become XLEN-aware (6 bits on RV64; reject or ignore `instr[25]` on RV32). Register-register **SLL/SRL/SRA** must use **`rs2[5:0]`** on RV64 (shift unit already uses `xlen_log` bits of `rs2` — verify 6 bits).

**Tests:** `rv64ui/{slli,srli,srai}.S` (64-bit shamt cases)

### 3.3a RV64I — LUI / AUIPC semantics (existing opcodes, changed behavior)

Not new encodings, but RV64 semantics differ from RV32 (`rv64.adoc`):

| Instruction | RV64 behavior |
|-------------|---------------|
| **LUI** | `{imm[31:12], 12'b0}` as a 32-bit value, then **sign-extended to 64 bits** |
| **AUIPC** | Same 32-bit offset formation, sign-extended to 64, added to `pc` |

Decoder currently does `uimm20 << (xlen - 20)` for U-type immediates, which is correct for RV32 but **incorrect for RV64** (places immediate at `[63:44]` instead of sign-extending `[31:0]`). Fix in `instr_decoder.py` and/or LUI lowering.

### 3.4 RV64M — word multiply/divide (5 new, all `OP-32`)

All operate on **lower 32 bits** of rs1/rs2; result sign-extended.

| Instruction | Opcode | funct3 | funct7 |
|-------------|--------|--------|--------|
| **MULW** | OP-32 | MUL (000) | 0000001 |
| **DIVW** | OP-32 | DIV (100) | 0000001 |
| **DIVUW** | OP-32 | DIVU (101) | 0000001 |
| **REMW** | OP-32 | REM (110) | 0000001 |
| **REMUW** | OP-32 | REMU (111) | 0000001 |

`MULW` handling is already sketched in comments in `mul_unit.py`.

**Tests:** `rv64um/{mulw,divw,divuw,remw,remuw}.S`

### 3.5 RV64A — 64-bit atomics (10 new opcodes + LR/SC.D)

Same AMO funct5 as `.w`, but **`funct3 = D (011)`**:

`amoswap.d`, `amoadd.d`, `amoand.d`, `amoor.d`, `amoxor.d`, `amomax.d`, `amomaxu.d`, `amomin.d`, `amominu.d`, plus **`lr.d` / `sc.d`**.

LSU atomic wrapper currently hardcodes `Funct3.W` for AMO stores.

On RV64, **LR.W / SC.W** remain valid and must **sign-extend** the loaded word into `rd` (in addition to new **LR.D / SC.D**).

**Tests:** `rv64ua/amo*_d.S`, `lrsc` (includes `.d` cases)

### 3.6 RV64 Zba — `*_uw` / `slli.uw` (5 new)

| Instruction | Notes |
|-------------|-------|
| **ADD.UW** | Add zero-extended 32-bit rs1 to rs2 |
| **SH1ADD.UW** | Same pattern |
| **SH2ADD.UW** | |
| **SH3ADD.UW** | |
| **SLLI.UW** | Shift left unsigned word |

RVC `C.ZEXT.W` expansion is blocked pending this:

```python
zext_w = (IllegalInstr(), 0)  # FIXME: Update when ADD.UW is implemented for RV64+
```

(`coreblocks/frontend/decoder/rvc.py`)

**Tests:** `rv64uzba/{add_uw,sh1add_uw,sh2add_uw,sh3add_uw,slli_uw}.S`

### 3.7 RV64 Zbb — word-sized and 64-bit variants (11 new)

| Instruction | Category |
|-------------|----------|
| **CLZW**, **CTZW**, **CPOPW** | Unary, 32-bit input |
| **ROLW**, **RORW**, **RORIW** | Rotates on low 32 bits |
| **REV8** (64-bit funct12) | Already have `REV8_32`; need `REV8_64` (`Funct12.REV8_64`) |
| **ORC.B** | Already present; verify 64-bit behavior |

**Tests:** `rv64uzbb/{clzw,ctzw,cpopw,rolw,rorw,roriw,rev8,…}.S`

### 3.8 RV64 Zbkb — pack / brev8 (optional; not in current `full` config)

Extension **Zbkb** is separate from the `B` → {Zba, Zbb, Zbs} implication. Only needed if Zbkb is added to `CoreConfiguration`.

| Instruction | Extension | Notes |
|-------------|-----------|-------|
| **PACK** | Zbkb | RV32 + RV64 |
| **PACKH** | Zbkb | RV32 + RV64 |
| **PACKW** | Zbkb | **RV64 only** (`OP-32`) |
| **BREV8** | Zbkb | Distinct from Zbb **REV8** (different encoding and spec) |

**Tests:** `rv64uzbkb/{pack,packh,packw,brev8}.S` (skip unless Zbkb enabled)

### 3.9 No new RV64-specific instructions expected in

- **Zbc** (`clmul*`) — same encodings, 64-bit operands
- **Zbkx** (`xperm4/8`) — same encodings
- **Zbs** — same encodings
- **Zicond** — same encodings
- **Zcb** compressed loads/stores — RV64 uses `c.ld`/`c.sd`/`c.ldsp`/`c.sdsp` (RVC already expands these)

---

## 4. Core Implementation Workstreams

### 4.1 Configuration & ISA plumbing

1. Add preset configs, e.g. `full64 = full.replace(xlen=64, phys_addr_bits=56)` and optionally `basic64`.
2. Gate RV64-only encodings in the decoder when `xlen != 64` (and treat `OP32`/`OP_IMM_32` as illegal on RV32).
3. Update `test/params/test_configurations.py` expected ISA strings.
4. Document `xlen=64` in README (currently says RV32 only).

### 4.2 Frontend / decoder (`instr_decoder.py`, `instr_description.py`)

1. Add `Opcode.OP_IMM_32` → `InstrType.I`, `Opcode.OP32` → `InstrType.R` in the type switch.
2. Register all encodings from §3 in `instructions_by_optype` (possibly grouped under existing `OpType`s).
3. Fix **shift immediate extraction**:
   - RV64 `OP-IMM` shifts: 6-bit shamt in `instr[25:20]`
   - RV32 `OP-IMM` shifts: 5-bit in `instr[24:20]`, `instr[25]` must be 0
   - `OP-IMM-32` shifts: 5-bit; `imm[5]≠0` is **reserved** per spec
4. Fix **U-type immediates** for RV64: LUI/AUIPC must sign-extend the 32-bit formed immediate, not shift U-field to `[63:44]`.
5. Optionally add explicit illegal detection for W-ops on RV32 and `OP32`/`OP_IMM_32` on RV32 (should fall out naturally if not in `supported_encodings`).
6. RVC: wire `zext_w` → `ADD.UW` once Zba is implemented.

### 4.3 Functional units

| Unit | Work |
|------|------|
| **ALU** | Add `ADDW`, `SUBW`, `ADDIW`; Zba `*_UW`, `SLLI.UW`; Zbb `*W` unary/rotates; Zbkb `PACK*`/`BREV8`; shared **sext32** helper for all W results |
| **Shift unit** | Add `SLLW/SRLW/SRAW/SLLIW/SRLIW/SRAIW`; W shifts operate on low 32 bits, sext result; RV64 non-W shifts already use `xlen_log` |
| **Mul unit** | Enable `MULW` (commented code); truncate inputs to 32 bits before multiply |
| **Div unit** | Add `DIVW/DIVUW/REMW/REMUW`; operate on low 32 bits of operands; **all W results sign-extended** (including `REMUW` and divide-by-zero cases per `m-st-ext.adoc`) |
| **LSU / requester** | Add `Funct3.D` + `LWU`; 8-byte alignment checks; byte masks `0xFF`; fix **`paddr >> bytes_in_word_log`** (currently hardcoded `>> 2`); **`LW` sign-extends on RV64**; `LD` returns full 64-bit word |
| **Atomic wrapper** | Propagate `funct3` from AMO encoding; support `.d` width; **LR.W sign-extends on RV64** |
| **FUs unchanged** | Jump, branch, CSR, exception, Zbc, Zbkx, Zbs (except operand width, which follows `xlen`) |

Common W-result pattern:

```
result64 = sext32(op32(rs1[31:0], rs2[31:0]))
```

### 4.4 Memory / bus subsystem

`GenParams` already sets 64-bit Wishbone when `xlen=64`, but **LSU address translation to bus is wrong**:

```python
self.bus.request_write(m, addr=paddr >> 2, data=bus_data, sel=bytes_mask)
self.bus.request_read(m, addr=paddr >> 2, sel=bytes_mask)
```

Should use `exact_log2(gen_params.isa.xlen // 8)` (I-cache already does this correctly).

Also audit:

- Test memory models (`test/test_core.py` uses `WishboneMemorySlave(..., shape=32)` — must follow `wb_params.data_width`)
- Regression memory / cocotb harness
- LiteX SoC integration (external repos; bus width must match)

### 4.5 Privileged architecture / MMU (mostly ready, needs RV64 validation)

Already parameterized:

- `medelegh` only on RV32; RV64 uses full 64-bit `medeleg`
- RV64 PTE format in page walker
- `SatpMode` SV39/48/57

Gaps for **RV64 Linux / arch-tests** (later phase):

- Default `supported_vm_schemes` is `BARE` only — need `SV39` (minimum) for Linux
- Walker asserts `SV64` mode unsupported (128-bit VA — fine to defer)
- `coreblocks.yaml` arch-test config: `UXLEN/SXLEN/MXLEN: 32`, `PHYS_ADDR_WIDTH: 32`, `STVAL_WIDTH/MTVAL_WIDTH: 32` — all need RV64 variants
- Supervisor tests: `rv64si/*`, `rv64mi/*`, `rv64ssvnapot/*` (when enabling Svnapot)

### 4.6 Scheduler / decode dispatch

Likely minimal changes if new ops reuse existing `OpType`s. If you introduce distinct op types (e.g. `ARITHMETIC_W`), update:

- `optypes_by_extensions` in `coreblocks/arch/optypes.py`
- FU decoder routing in `fu_decoder.py`
- RS assignment in configurations (probably same FUs as RV32 counterparts)

**Recommended approach:** reuse existing `OpType`s and extend FU decoder managers (matches current MUL/DIV pattern).

---

## 5. Testing Plan

### 5.1 Unit tests (pysim, fast feedback)

| Test file | Add / extend |
|-----------|--------------|
| `test/frontend/test_instr_decoder.py` | All §3 encodings at `xlen=64`; illegality at `xlen=32` |
| `test/frontend/test_rvc.py` | Already has `rv64ic` — keep in sync |
| `test/func_blocks/fu/test_alu.py`, `test_shift_unit.py`, `test_mul_unit.py`, `test_div_unit.py` | W-variant and RV64 Z-ext cases |
| `test/func_blocks/fu/lsu/*` | `ld`/`sd`/`lwu`, alignment faults |
| `test/test_core.py` | RV64 asm snippets; fix memory slave width |

### 5.2 Assembly integration tests

Add `test/asm/rv64_*.asm` smoke tests (similar to existing `fibonacci.asm`, `csr.asm`):

- W-arithmetic chain
- `ld`/`sd` roundtrip
- AMO.D smoke (if A enabled)

Toolchain: already uses `riscv64-unknown-elf-as` in `test/test_core.py`.

### 5.3 `riscv-tests` regression

Extend `test/external/riscv-tests/Makefile` (currently **RV32-only**):

```
rv32ui, rv32um, rv32ua, rv32uc, rv32uz*, …
```

Add parallel RV64 targets mirroring upstream Makefrags:

| Suite | Tests |
|-------|-------|
| `rv64ui` | 37 scalar tests (see `rv64ui/Makefrag`) |
| `rv64um` | 9 tests |
| `rv64ua` | 17 tests (+ lrsc) |
| `rv64uc` | compressed |
| `rv64uzba/b/bc/bkb/bkx/bs/icond` | bitmanip |
| `rv64si`, `rv64mi` | supervisor/machine (when S mode + VM enabled) |

Build flags: `-march=rv64gc… -mabi=lp64(d)`.

### 5.4 `riscv-arch-test` (ACT)

Create `coreblocks-full-rv64.yaml` (or extend existing):

- `UXLEN/SXLEN/MXLEN: 64`
- `PHYS_ADDR_WIDTH: 56` (or chosen PA width)
- `STVAL_WIDTH/MTVAL_WIDTH: 64`
- Enable `Ssu64xl` extension entry
- SATP modes when VM is ready

CI job `run-arch-regression-tests` should matrix over `{rv32, rv64}` or add dedicated RV64 job.

---

## 6. CI, Synthesis & FPGA

### 6.1 CI (`.github/workflows/main.yml`)

Current pipeline (all RV32):

- Synthesize `full` → `core.v`
- Build/run `riscv-tests` (RV32 Makefile)
- Run arch-tests with RV32 yaml
- Unit tests

**Needed for RV64:**

| Job | Change |
|-----|--------|
| `build-core` | Matrix: `{config: full, xlen: 64}` or separate `full64` artifact |
| `build-regression-tests` | Build RV64 `riscv-tests` ELFs (`XLEN=64` or separate make target) |
| `run-regression-tests` | Run RV64 suite against RV64 Verilog |
| `build/run-arch-regression-tests` | RV64 yaml + ELFs |
| `unit-test` | Include RV64 parametrized cases |
| `lint` | unchanged |

Consider **split CI strategy**:

- **Fast path (every PR):** RV64 pysim unit tests + small RV64 smoke subset
- **Full path (nightly or label):** complete `rv64*` regression + arch-tests

### 6.2 Synthesis benchmarks (`benchmark.yml`)

Currently synthesizes `basic` and `full` on **ECP5** only.

RV64 impact:

- ~2× register file, LSU, bypass network width
- Larger multipliers/dividers
- May **reduce Fmax** and **increase LC count** significantly

Plan:

1. Add `full64` to synthesis matrix once core elaborates cleanly.
2. Track separate benchmark series (`Fmax and LCs (full64)`).
3. Evaluate whether ECP5-85K is still sufficient or if a **larger FPGA target** (e.g. Xilinx UltraScale+, Intel Agilex) should be added to the synth container for realistic RV64+OoO sizing.

### 6.3 FPGA deployment

Not in this repo, but downstream effects:

- LiteX SoC wrapper must expose 64-bit Wishbone
- Boot firmware / OpenSBI built `rv64imac…`
- Device tree `#address-cells` / `reg` widths
- Potentially larger BRAM requirements for test bitstreams

Embench currently hardcoded `riscv32` (`test/external/embench/Makefile`) — add `riscv64` board config when perf comparisons matter.

---

## 7. Suggested Implementation Phases

```
Phase 0: Config + bus fixes
    ↓
Phase 1: RV64I base (W-ops, ld/sd/lwu, 6-bit shifts)
    ↓
Phase 2: RV64M (*W mul/div)
    ↓
Phase 3: RV64 CI build
    ↓
Phase 4: RV64A (AMO/LR/SC .d)
    ↓
Phase 5: RV64 B extensions (Zba/Zbb/Zbkb RV64 variants)
    ↓
Phase 6: S-mode + SV39 + arch-tests
    ↓
Phase 7: FPGA / Linux bring-up
```

| Phase | Deliverable | Verification |
|-------|-------------|--------------|
| **0** | `full64` config; LSU `>> word_log`; LUI/AUIPC fix; test memory width | Elaboration + existing RV32 regressions still pass |
| **1** | RV64I W-ops + 6-bit shifts + `ld/sd/lwu` + `LW` sext | `rv64ui-*` |
| **2** | `MULW`, `DIV*W`, `REM*W` | `rv64um-*` |
| **3** | RV64 CI build of core + tests | GitHub Actions matrix |
| **4** | AMO/LR/SC `.d` | `rv64ua-*` |
| **5** | Zba `*_uw`, Zbb `*w` (+ Zbkb if enabled) | `rv64uzba/b/*` (+ `rv64uzbkb/*` optional) |
| **6** | `SV39`, updated arch-test yaml | `riscv-arch-test` + `rv64si/mi` |
| **7** | Larger FPGA synth target; LiteX/Linux | External bring-up |

---

## 8. Risk Notes

1. **W-operation semantics** — easy to get wrong (forget sign-extension); prioritize `rv64ui/addw.S`, `subw.S`, `addiw.S` early.
2. **LUI/AUIPC on RV64** — wrong immediate placement breaks address formation and constant loading.
3. **LSU bus addressing** — silent corruption if `>> 2` left in place on 64-bit bus.
4. **Decoder shift immediates** — RV64 `SLLI` with shamt > 31 will fail until 6-bit decode is fixed.
5. **LW vs LWU on RV64** — `LW` must sign-extend; confusing with `LWU` zero-extend.
6. **Resource explosion** — RV64 OoO on ECP5 may not fit `full` config; may need `full64` with reduced superscalarity for FPGA.
7. **Dual maintenance** — long term, parametrize tests over `xlen` rather than duplicating RV32/RV64 suites.

---

## 9. Instruction Checklist (Quick Reference)

**Must implement for `full` → `full64` parity (≈44 distinct mnemonics + 2 semantic fixes):**

- **I loads/stores (new):** `ld`, `lwu`, `sd`
- **I semantic fixes (existing opcodes):** `lui`, `auipc` (RV64 sign-extension); `lw` (RV64 sign-extension); `slli`/`srli`/`srai` (6-bit shamt)
- **I W-arith/shift (new):** `addiw`, `addw`, `subw`, `slliw`, `sllw`, `srliw`, `srlw`, `sraiw`, `sraw`
- **M W (new, `OP-32`):** `mulw`, `divw`, `divuw`, `remw`, `remuw`
- **A D (new):** 9× `amo*.d` + `lr.d` + `sc.d` (plus correct **LR.W** sign-extension on RV64)
- **Zba (RV64-only):** `add.uw`, `sh1add.uw`, `sh2add.uw`, `sh3add.uw`, `slli.uw`
- **Zbb (RV64-only):** `clzw`, `ctzw`, `cpopw`, `rolw`, `rorw`, `roriw`, `rev8` (64-bit `Funct12` encoding)

**Optional (Zbkb, not in current `full`):** `pack`, `packh`, `packw`, `brev8`

Everything else in the current `full` config should **carry over unchanged** at 64-bit width once decoding, LUI/AUIPC, and LSU are fixed.
