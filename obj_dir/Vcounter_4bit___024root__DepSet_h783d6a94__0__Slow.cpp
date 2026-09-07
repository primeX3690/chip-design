// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_4bit.h for the primary calling header

#include "Vcounter_4bit__pch.h"
#include "Vcounter_4bit___024root.h"

VL_ATTR_COLD void Vcounter_4bit___024root___eval_static__TOP(Vcounter_4bit___024root* vlSelf);

VL_ATTR_COLD void Vcounter_4bit___024root___eval_static(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_static\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    Vcounter_4bit___024root___eval_static__TOP(vlSelf);
}

VL_ATTR_COLD void Vcounter_4bit___024root___eval_static__TOP(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_static__TOP\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    vlSelfRef.counter_4bit_tb__DOT__errors = 0U;
}

VL_ATTR_COLD void Vcounter_4bit___024root___eval_final(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_final\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
}

VL_ATTR_COLD void Vcounter_4bit___024root___eval_settle(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_settle\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_4bit___024root___dump_triggers__act(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___dump_triggers__act\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((1U & (~ vlSelfRef.__VactTriggered.any()))) {
        VL_DBG_MSGF("         No triggers active\n");
    }
    if ((1ULL & vlSelfRef.__VactTriggered.word(0U))) {
        VL_DBG_MSGF("         'act' region trigger index 0 is active: @(posedge counter_4bit_tb.clk)\n");
    }
    if ((2ULL & vlSelfRef.__VactTriggered.word(0U))) {
        VL_DBG_MSGF("         'act' region trigger index 1 is active: @(negedge counter_4bit_tb.rst_n)\n");
    }
    if ((4ULL & vlSelfRef.__VactTriggered.word(0U))) {
        VL_DBG_MSGF("         'act' region trigger index 2 is active: @(negedge counter_4bit_tb.clk)\n");
    }
    if ((8ULL & vlSelfRef.__VactTriggered.word(0U))) {
        VL_DBG_MSGF("         'act' region trigger index 3 is active: @([true] __VdlySched.awaitingCurrentTime())\n");
    }
}
#endif  // VL_DEBUG

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_4bit___024root___dump_triggers__nba(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___dump_triggers__nba\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((1U & (~ vlSelfRef.__VnbaTriggered.any()))) {
        VL_DBG_MSGF("         No triggers active\n");
    }
    if ((1ULL & vlSelfRef.__VnbaTriggered.word(0U))) {
        VL_DBG_MSGF("         'nba' region trigger index 0 is active: @(posedge counter_4bit_tb.clk)\n");
    }
    if ((2ULL & vlSelfRef.__VnbaTriggered.word(0U))) {
        VL_DBG_MSGF("         'nba' region trigger index 1 is active: @(negedge counter_4bit_tb.rst_n)\n");
    }
    if ((4ULL & vlSelfRef.__VnbaTriggered.word(0U))) {
        VL_DBG_MSGF("         'nba' region trigger index 2 is active: @(negedge counter_4bit_tb.clk)\n");
    }
    if ((8ULL & vlSelfRef.__VnbaTriggered.word(0U))) {
        VL_DBG_MSGF("         'nba' region trigger index 3 is active: @([true] __VdlySched.awaitingCurrentTime())\n");
    }
}
#endif  // VL_DEBUG

VL_ATTR_COLD void Vcounter_4bit___024root___ctor_var_reset(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___ctor_var_reset\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    vlSelf->counter_4bit_tb__DOT__clk = VL_RAND_RESET_I(1);
    vlSelf->counter_4bit_tb__DOT__rst_n = VL_RAND_RESET_I(1);
    vlSelf->counter_4bit_tb__DOT__en = VL_RAND_RESET_I(1);
    vlSelf->counter_4bit_tb__DOT__count = VL_RAND_RESET_I(4);
    vlSelf->counter_4bit_tb__DOT__errors = VL_RAND_RESET_I(32);
    vlSelf->__Vtrigprevexpr___TOP__counter_4bit_tb__DOT__clk__0 = VL_RAND_RESET_I(1);
    vlSelf->__Vtrigprevexpr___TOP__counter_4bit_tb__DOT__rst_n__0 = VL_RAND_RESET_I(1);
}
