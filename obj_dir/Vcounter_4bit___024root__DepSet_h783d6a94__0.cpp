// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_4bit.h for the primary calling header

#include "Vcounter_4bit__pch.h"
#include "Vcounter_4bit___024root.h"

VlCoroutine Vcounter_4bit___024root___eval_initial__TOP__Vtiming__0(Vcounter_4bit___024root* vlSelf);
VlCoroutine Vcounter_4bit___024root___eval_initial__TOP__Vtiming__1(Vcounter_4bit___024root* vlSelf);

void Vcounter_4bit___024root___eval_initial(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_initial\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    Vcounter_4bit___024root___eval_initial__TOP__Vtiming__0(vlSelf);
    Vcounter_4bit___024root___eval_initial__TOP__Vtiming__1(vlSelf);
    vlSelfRef.__Vtrigprevexpr___TOP__counter_4bit_tb__DOT__clk__0 
        = vlSelfRef.counter_4bit_tb__DOT__clk;
    vlSelfRef.__Vtrigprevexpr___TOP__counter_4bit_tb__DOT__rst_n__0 
        = vlSelfRef.counter_4bit_tb__DOT__rst_n;
}

VL_INLINE_OPT VlCoroutine Vcounter_4bit___024root___eval_initial__TOP__Vtiming__0(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_initial__TOP__Vtiming__0\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Init
    CData/*3:0*/ counter_4bit_tb__DOT__expected;
    counter_4bit_tb__DOT__expected = 0;
    // Body
    vlSelfRef.counter_4bit_tb__DOT__clk = 0U;
    vlSelfRef.counter_4bit_tb__DOT__rst_n = 0U;
    vlSelfRef.counter_4bit_tb__DOT__en = 0U;
    counter_4bit_tb__DOT__expected = 0U;
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         33);
    vlSelfRef.counter_4bit_tb__DOT__rst_n = 1U;
    vlSelfRef.counter_4bit_tb__DOT__en = 1U;
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 0: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 1: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 2: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 3: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 4: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 5: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 6: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 7: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 8: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 9: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 10: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 11: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 12: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 13: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 14: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 15: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 16: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 17: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 18: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         39);
    counter_4bit_tb__DOT__expected = (0xfU & ((IData)(1U) 
                                              + (IData)(counter_4bit_tb__DOT__expected)));
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH at step 19: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    vlSelfRef.counter_4bit_tb__DOT__en = 0U;
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         50);
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH (en=0 hold) at step 0: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         50);
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH (en=0 hold) at step 1: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         50);
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH (en=0 hold) at step 2: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         50);
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH (en=0 hold) at step 3: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         50);
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH (en=0 hold) at step 4: expected=%b got=%b\n",0,
                     4,counter_4bit_tb__DOT__expected,
                     4,(IData)(vlSelfRef.counter_4bit_tb__DOT__count));
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    vlSelfRef.counter_4bit_tb__DOT__en = 1U;
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         59);
    vlSelfRef.counter_4bit_tb__DOT__rst_n = 0U;
    co_await vlSelfRef.__VtrigSched_hfaec0dfa__0.trigger(0U, 
                                                         nullptr, 
                                                         "@(negedge counter_4bit_tb.clk)", 
                                                         "tests/counter_4bit_tb.v", 
                                                         61);
    counter_4bit_tb__DOT__expected = 0U;
    if (VL_UNLIKELY(((IData)(vlSelfRef.counter_4bit_tb__DOT__count) 
                     != (IData)(counter_4bit_tb__DOT__expected)))) {
        VL_WRITEF_NX("MISMATCH (reset) got=%b\n",0,
                     4,vlSelfRef.counter_4bit_tb__DOT__count);
        vlSelfRef.counter_4bit_tb__DOT__errors = ((IData)(1U) 
                                                  + vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    vlSelfRef.counter_4bit_tb__DOT__rst_n = 1U;
    if ((0U == vlSelfRef.counter_4bit_tb__DOT__errors)) {
        VL_WRITEF_NX("PASS: counter_4bit_tb \342\200\224 all checks correct\n",0);
    } else {
        VL_WRITEF_NX("FAIL: counter_4bit_tb \342\200\224 %0d mismatches\n",0,
                     32,vlSelfRef.counter_4bit_tb__DOT__errors);
    }
    VL_FINISH_MT("tests/counter_4bit_tb.v", 74, "");
}

VL_INLINE_OPT VlCoroutine Vcounter_4bit___024root___eval_initial__TOP__Vtiming__1(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_initial__TOP__Vtiming__1\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    while (1U) {
        co_await vlSelfRef.__VdlySched.delay(5ULL, 
                                             nullptr, 
                                             "tests/counter_4bit_tb.v", 
                                             25);
        vlSelfRef.counter_4bit_tb__DOT__clk = (1U & 
                                               (~ (IData)(vlSelfRef.counter_4bit_tb__DOT__clk)));
    }
}

void Vcounter_4bit___024root___eval_act(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_act\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
}

void Vcounter_4bit___024root___nba_sequent__TOP__0(Vcounter_4bit___024root* vlSelf);

void Vcounter_4bit___024root___eval_nba(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_nba\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((3ULL & vlSelfRef.__VnbaTriggered.word(0U))) {
        Vcounter_4bit___024root___nba_sequent__TOP__0(vlSelf);
    }
}

VL_INLINE_OPT void Vcounter_4bit___024root___nba_sequent__TOP__0(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___nba_sequent__TOP__0\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if (vlSelfRef.counter_4bit_tb__DOT__rst_n) {
        if (vlSelfRef.counter_4bit_tb__DOT__en) {
            vlSelfRef.counter_4bit_tb__DOT__count = 
                (0xfU & ((IData)(1U) + (IData)(vlSelfRef.counter_4bit_tb__DOT__count)));
        }
    } else {
        vlSelfRef.counter_4bit_tb__DOT__count = 0U;
    }
}

void Vcounter_4bit___024root___timing_resume(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___timing_resume\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((4ULL & vlSelfRef.__VactTriggered.word(0U))) {
        vlSelfRef.__VtrigSched_hfaec0dfa__0.resume(
                                                   "@(negedge counter_4bit_tb.clk)");
    }
    if ((8ULL & vlSelfRef.__VactTriggered.word(0U))) {
        vlSelfRef.__VdlySched.resume();
    }
}

void Vcounter_4bit___024root___timing_commit(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___timing_commit\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Body
    if ((! (4ULL & vlSelfRef.__VactTriggered.word(0U)))) {
        vlSelfRef.__VtrigSched_hfaec0dfa__0.commit(
                                                   "@(negedge counter_4bit_tb.clk)");
    }
}

void Vcounter_4bit___024root___eval_triggers__act(Vcounter_4bit___024root* vlSelf);

bool Vcounter_4bit___024root___eval_phase__act(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_phase__act\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Init
    VlTriggerVec<4> __VpreTriggered;
    CData/*0:0*/ __VactExecute;
    // Body
    Vcounter_4bit___024root___eval_triggers__act(vlSelf);
    Vcounter_4bit___024root___timing_commit(vlSelf);
    __VactExecute = vlSelfRef.__VactTriggered.any();
    if (__VactExecute) {
        __VpreTriggered.andNot(vlSelfRef.__VactTriggered, vlSelfRef.__VnbaTriggered);
        vlSelfRef.__VnbaTriggered.thisOr(vlSelfRef.__VactTriggered);
        Vcounter_4bit___024root___timing_resume(vlSelf);
        Vcounter_4bit___024root___eval_act(vlSelf);
    }
    return (__VactExecute);
}

bool Vcounter_4bit___024root___eval_phase__nba(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_phase__nba\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Init
    CData/*0:0*/ __VnbaExecute;
    // Body
    __VnbaExecute = vlSelfRef.__VnbaTriggered.any();
    if (__VnbaExecute) {
        Vcounter_4bit___024root___eval_nba(vlSelf);
        vlSelfRef.__VnbaTriggered.clear();
    }
    return (__VnbaExecute);
}

#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_4bit___024root___dump_triggers__nba(Vcounter_4bit___024root* vlSelf);
#endif  // VL_DEBUG
#ifdef VL_DEBUG
VL_ATTR_COLD void Vcounter_4bit___024root___dump_triggers__act(Vcounter_4bit___024root* vlSelf);
#endif  // VL_DEBUG

void Vcounter_4bit___024root___eval(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
    // Init
    IData/*31:0*/ __VnbaIterCount;
    CData/*0:0*/ __VnbaContinue;
    // Body
    __VnbaIterCount = 0U;
    __VnbaContinue = 1U;
    while (__VnbaContinue) {
        if (VL_UNLIKELY((0x64U < __VnbaIterCount))) {
#ifdef VL_DEBUG
            Vcounter_4bit___024root___dump_triggers__nba(vlSelf);
#endif
            VL_FATAL_MT("tests/counter_4bit_tb.v", 8, "", "NBA region did not converge.");
        }
        __VnbaIterCount = ((IData)(1U) + __VnbaIterCount);
        __VnbaContinue = 0U;
        vlSelfRef.__VactIterCount = 0U;
        vlSelfRef.__VactContinue = 1U;
        while (vlSelfRef.__VactContinue) {
            if (VL_UNLIKELY((0x64U < vlSelfRef.__VactIterCount))) {
#ifdef VL_DEBUG
                Vcounter_4bit___024root___dump_triggers__act(vlSelf);
#endif
                VL_FATAL_MT("tests/counter_4bit_tb.v", 8, "", "Active region did not converge.");
            }
            vlSelfRef.__VactIterCount = ((IData)(1U) 
                                         + vlSelfRef.__VactIterCount);
            vlSelfRef.__VactContinue = 0U;
            if (Vcounter_4bit___024root___eval_phase__act(vlSelf)) {
                vlSelfRef.__VactContinue = 1U;
            }
        }
        if (Vcounter_4bit___024root___eval_phase__nba(vlSelf)) {
            __VnbaContinue = 1U;
        }
    }
}

#ifdef VL_DEBUG
void Vcounter_4bit___024root___eval_debug_assertions(Vcounter_4bit___024root* vlSelf) {
    (void)vlSelf;  // Prevent unused variable warning
    Vcounter_4bit__Syms* const __restrict vlSymsp VL_ATTR_UNUSED = vlSelf->vlSymsp;
    VL_DEBUG_IF(VL_DBG_MSGF("+    Vcounter_4bit___024root___eval_debug_assertions\n"); );
    auto& vlSelfRef = std::ref(*vlSelf).get();
}
#endif  // VL_DEBUG
