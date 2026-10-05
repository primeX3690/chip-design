"""evohdl.eda -- a small, tool-independent logic-level EDA kernel (pure Python, no external binaries).

Pipeline:  Verilog subset --(hdl parser)--> AST --(elaborate)--> AIG --(opt)--> AIG --(techmap + liberty)--> Netlist
           --(sta + sdc, power)--> reports;   sat/cec/bmc prove two designs equivalent without Yosys.
Scope: combinational + simple synchronous sequential logic at gate level. Physical design (placement, routing,
LEF/DEF/GDS, physical DRC/LVS) is intentionally NOT here -- see README "EDA kernel" for why.
"""
