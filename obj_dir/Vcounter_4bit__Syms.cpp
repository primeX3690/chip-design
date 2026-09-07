// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table implementation internals

#include "Vcounter_4bit__pch.h"
#include "Vcounter_4bit.h"
#include "Vcounter_4bit___024root.h"

// FUNCTIONS
Vcounter_4bit__Syms::~Vcounter_4bit__Syms()
{
}

Vcounter_4bit__Syms::Vcounter_4bit__Syms(VerilatedContext* contextp, const char* namep, Vcounter_4bit* modelp)
    : VerilatedSyms{contextp}
    // Setup internal state of the Syms class
    , __Vm_modelp{modelp}
    // Setup module instances
    , TOP{this, namep}
{
        // Check resources
        Verilated::stackCheck(12);
    // Configure time unit / time precision
    _vm_contextp__->timeunit(-12);
    _vm_contextp__->timeprecision(-12);
    // Setup each module's pointers to their submodules
    // Setup each module's pointer back to symbol table (for public functions)
    TOP.__Vconfigure(true);
}
