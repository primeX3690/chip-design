// Verilated -*- C++ -*-
// DESCRIPTION: Verilator output: Symbol table internal header
//
// Internal details; most calling programs do not need this header,
// unless using verilator public meta comments.

#ifndef VERILATED_VCOUNTER_4BIT__SYMS_H_
#define VERILATED_VCOUNTER_4BIT__SYMS_H_  // guard

#include "verilated.h"

// INCLUDE MODEL CLASS

#include "Vcounter_4bit.h"

// INCLUDE MODULE CLASSES
#include "Vcounter_4bit___024root.h"

// SYMS CLASS (contains all model state)
class alignas(VL_CACHE_LINE_BYTES)Vcounter_4bit__Syms final : public VerilatedSyms {
  public:
    // INTERNAL STATE
    Vcounter_4bit* const __Vm_modelp;
    VlDeleter __Vm_deleter;
    bool __Vm_didInit = false;

    // MODULE INSTANCE STATE
    Vcounter_4bit___024root        TOP;

    // CONSTRUCTORS
    Vcounter_4bit__Syms(VerilatedContext* contextp, const char* namep, Vcounter_4bit* modelp);
    ~Vcounter_4bit__Syms();

    // METHODS
    const char* name() { return TOP.name(); }
};

#endif  // guard
