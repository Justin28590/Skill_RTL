ENTRY(_start)
SECTIONS { . = 0; .text : { *(.text.start) *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) *(.sdata*) } .bss : { *(.bss*) *(.sbss*) } /DISCARD/ : { *(.riscv.attributes) *(.comment) } }
