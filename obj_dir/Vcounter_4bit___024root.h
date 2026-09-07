// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design internal header
// See Vcounter_4bit.h for the primary calling header

#ifndef VERILATED_VCOUNTER_4BIT___024ROOT_H_
#define VERILATED_VCOUNTER_4BIT___024ROOT_H_  // guard

#include "verilated.h"
#include "verilated_timing.h"


class Vcounter_4bit__Syms;

class alignas(VL_CACHE_LINE_BYTES) Vcounter_4bit___024root final : public VerilatedModule {
  public:

    // DESIGN SPECIFIC STATE
    CData/*0:0*/ counter_4bit_tb__DOT__clk;
    CData/*0:0*/ counter_4bit_tb__DOT__rst_n;
    CData/*0:0*/ counter_4bit_tb__DOT__en;
    CData/*3:0*/ counter_4bit_tb__DOT__count;
    CData/*0:0*/ __Vtrigprevexpr___TOP__counter_4bit_tb__DOT__clk__0;
    CData/*0:0*/ __Vtrigprevexpr___TOP__counter_4bit_tb__DOT__rst_n__0;
    CData/*0:0*/ __VactContinue;
    IData/*31:0*/ counter_4bit_tb__DOT__errors;
    IData/*31:0*/ __VactIterCount;
    VlDelayScheduler __VdlySched;
    VlTriggerScheduler __VtrigSched_hfaec0dfa__0;
    VlTriggerVec<4> __VactTriggered;
    VlTriggerVec<4> __VnbaTriggered;

    // INTERNAL VARIABLES
    Vcounter_4bit__Syms* const vlSymsp;

    // CONSTRUCTORS
    Vcounter_4bit___024root(Vcounter_4bit__Syms* symsp, const char* v__name);
    ~Vcounter_4bit___024root();
    VL_UNCOPYABLE(Vcounter_4bit___024root);

    // INTERNAL METHODS
    void __Vconfigure(bool first);
};


#endif  // guard
