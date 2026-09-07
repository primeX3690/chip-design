// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Design implementation internals
// See Vcounter_4bit.h for the primary calling header

#include "Vcounter_4bit__pch.h"
#include "Vcounter_4bit__Syms.h"
#include "Vcounter_4bit___024root.h"

void Vcounter_4bit___024root___ctor_var_reset(Vcounter_4bit___024root* vlSelf);

Vcounter_4bit___024root::Vcounter_4bit___024root(Vcounter_4bit__Syms* symsp, const char* v__name)
    : VerilatedModule{v__name}
    , __VdlySched{*symsp->_vm_contextp__}
    , vlSymsp{symsp}
 {
    // Reset structure values
    Vcounter_4bit___024root___ctor_var_reset(this);
}

void Vcounter_4bit___024root::__Vconfigure(bool first) {
    (void)first;  // Prevent unused variable warning
}

Vcounter_4bit___024root::~Vcounter_4bit___024root() {
}
