"""Generate libs/tiny_generic.lib -- an ILLUSTRATIVE standard-cell library (fictional numbers, NOT a real PDK).
Delay = intrinsic + r_drive*load + 0.25*input_slew, tabulated as NLDM so the STA code path is the real one."""
from pathlib import Path

SLEW = [0.02, 0.08, 0.30]
LOAD = [0.002, 0.010, 0.040]   # pF

def table(kind, d0, r, sf=0.25, out_slew=False):
    rows = []
    for s in SLEW:
        row = []
        for c in LOAD:
            row.append(round((0.02 + 0.5 * d0 + 0.8 * r * c * 10 + 0.1 * s) if out_slew else (d0 + r * c * 10 + sf * s), 4))
        rows.append('"' + ", ".join(str(x) for x in row) + '"')
    return (f'        {kind} (delay_template) {{\n          index_1 ("{", ".join(map(str, SLEW))}");\n'
            f'          index_2 ("{", ".join(map(str, LOAD))}");\n          values ({", ".join(rows)});\n        }}\n')

# name, area, leakage(nW), function, inputs, d0(ns), r(drive), sense per input
CELLS = [
    ("INV",   1.0, 0.5, "!A",           ["A"],           0.020, 0.9, "negative_unate"),
    ("BUF",   1.5, 0.7, "A",            ["A"],           0.040, 0.7, "positive_unate"),
    ("NAND2", 1.5, 0.8, "!(A&B)",       ["A", "B"],      0.030, 1.1, "negative_unate"),
    ("NOR2",  1.5, 0.8, "!(A|B)",       ["A", "B"],      0.036, 1.3, "negative_unate"),
    ("AND2",  2.0, 1.0, "A&B",          ["A", "B"],      0.055, 0.8, "positive_unate"),
    ("OR2",   2.0, 1.0, "A|B",          ["A", "B"],      0.060, 0.8, "positive_unate"),
    ("XOR2",  3.0, 1.6, "A^B",          ["A", "B"],      0.075, 1.0, "non_unate"),
    ("XNOR2", 3.0, 1.6, "!(A^B)",       ["A", "B"],      0.075, 1.0, "non_unate"),
    ("NAND3", 2.0, 1.1, "!(A&B&C)",     ["A", "B", "C"], 0.040, 1.3, "negative_unate"),
    ("NOR3",  2.0, 1.1, "!(A|B|C)",     ["A", "B", "C"], 0.050, 1.6, "negative_unate"),
    ("AOI21", 2.0, 1.0, "!((A&B)|C)",   ["A", "B", "C"], 0.045, 1.4, "negative_unate"),
    ("OAI21", 2.0, 1.0, "!((A|B)&C)",   ["A", "B", "C"], 0.045, 1.4, "negative_unate"),
    ("MUX2",  3.5, 1.8, "(S&B)|(!S&A)", ["A", "B", "S"], 0.070, 0.9, "non_unate"),
]

out = ['library (tiny_generic) {', '  time_unit : "1ns";', '  capacitance_load_unit (1, pf);', '  leakage_power_unit : "1nW";',
       '  nom_voltage : 1.0;', '  lu_table_template (delay_template) {', '    variable_1 : input_net_transition;',
       '    variable_2 : total_output_net_capacitance;', '  }', '']
for name, area, leak, fn, ins, d0, r, sense in CELLS:
    out.append(f'  cell ({name}) {{\n    area : {area};\n    cell_leakage_power : {leak};')
    for p in ins:
        out.append(f'    pin ({p}) {{ direction : input; capacitance : {0.0020 + 0.0003 * (1 if name not in ("INV","BUF") else 0)}; }}')
    out.append(f'    pin (Y) {{\n      direction : output;\n      function : "{fn}";')
    for p in ins:
        out.append(f'      timing () {{\n        related_pin : "{p}";\n        timing_sense : {sense};')
        out.append(table("cell_rise", d0, r) + table("cell_fall", d0 * 0.9, r * 0.95) +
                   table("rise_transition", d0, r, out_slew=True) + table("fall_transition", d0, r, out_slew=True) + "      }")
    out.append("    }\n  }\n")
# D flip-flop: clk->Q launch arc + setup check on D
out.append('''  cell (DFF) {
    area : 5.0;
    cell_leakage_power : 2.4;
    ff (IQ, IQN) { clocked_on : "CLK"; next_state : "D"; }
    pin (D) {
      direction : input; capacitance : 0.0025;
      timing () {
        related_pin : "CLK"; timing_type : setup_rising;
        rise_constraint (delay_template) { index_1 ("0.02, 0.08, 0.30"); index_2 ("0.02, 0.08, 0.30"); values ("0.04, 0.045, 0.06", "0.045, 0.05, 0.065", "0.06, 0.065, 0.08"); }
        fall_constraint (delay_template) { index_1 ("0.02, 0.08, 0.30"); index_2 ("0.02, 0.08, 0.30"); values ("0.05, 0.055, 0.07", "0.055, 0.06, 0.075", "0.07, 0.075, 0.09"); }
      }
    }
    pin (CLK) { direction : input; capacitance : 0.0030; }
    pin (Q) {
      direction : output; function : "IQ";
      timing () {
        related_pin : "CLK"; timing_type : rising_edge; timing_sense : non_unate;
''' + table("cell_rise", 0.12, 1.0) + table("cell_fall", 0.11, 1.0) + table("rise_transition", 0.12, 1.0, out_slew=True) +
           table("fall_transition", 0.11, 1.0, out_slew=True) + '''      }
    }
  }
''')
out.append("}")
Path(__file__).resolve().parent.parent.joinpath("libs", "tiny_generic.lib").write_text("\n".join(out) + "\n")
print("wrote libs/tiny_generic.lib")
