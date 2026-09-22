# run_sta.tcl
# Real static timing analysis using OpenSTA (https://github.com/parallaxsw/OpenSTA)
# against the actual SkyWater sky130_fd_sc_hd .lib timing model.
#
# This replaces yosys_synthesizer.py's `ltp` (longest topological path,
# measured in *logic levels*, technology-independent) with a real
# picosecond-accurate number: actual gate delays + actual wire-load
# estimates from the sky130 standard-cell library's liberty file.
#
# Usage (opensta_runner.py builds this exact invocation):
#   sta -no_init -exit \
#       -define "LIB_FILE=/path/to/sky130_fd_sc_hd__tt_025C_1v80.lib" \
#       -define "NETLIST_FILE=/path/to/synthesized_netlist.v" \
#       -define "TOP_MODULE=picorv32_alu" \
#       -define "CLOCK_PERIOD_NS=10.0" \
#       run_sta.tcl
#
# If the design has no clock (e.g. picorv32_alu / alu_basic are purely
# combinational), CLOCK_PORT is left undefined and this script instead
# reports max input-to-output combinational delay across all paths, which
# is the number that actually matters for a combinational block.

if { [info exists ::env(LIB_FILE)] } { set lib_file $::env(LIB_FILE) } else { set lib_file $LIB_FILE }
if { [info exists ::env(NETLIST_FILE)] } { set netlist_file $::env(NETLIST_FILE) } else { set netlist_file $NETLIST_FILE }
if { [info exists ::env(TOP_MODULE)] } { set top_module $::env(TOP_MODULE) } else { set top_module $TOP_MODULE }

read_liberty $lib_file
read_verilog $netlist_file
link_design $top_module

# If a clock port was provided, constrain it; otherwise this is a
# combinational block and we skip clock creation entirely.
if { [info exists ::env(CLOCK_PORT)] && $::env(CLOCK_PORT) ne "" } {
    set clk_port $::env(CLOCK_PORT)
    set clk_period $::env(CLOCK_PERIOD_NS)
    create_clock -name core_clk -period $clk_period [get_ports $clk_port]
    set_input_delay  -clock core_clk [expr {$clk_period * 0.1}] [all_inputs]
    set_output_delay -clock core_clk [expr {$clk_period * 0.1}] [all_outputs]
} else {
    # Combinational block: treat all inputs as available at t=0 and demand
    # all outputs settle within one nominal "virtual" clock period, purely
    # so report_checks has a reference to slack against. The absolute delay
    # numbers below (report_checks -path_delay max) are the real numbers
    # that matter, independent of this virtual constraint.
    set virtual_period $::env(CLOCK_PERIOD_NS)
    create_clock -name virtual_clk -period $virtual_period
    set_input_delay  -clock virtual_clk 0 [all_inputs]
    set_output_delay -clock virtual_clk 0 [all_outputs]
}

set_units -time ps

puts "EVOHDL_STA_BEGIN"
report_checks -path_delay max -digits 4
report_checks -path_delay min -digits 4
report_tns -digits 4
report_wns -digits 4
puts "EVOHDL_STA_END"

exit
