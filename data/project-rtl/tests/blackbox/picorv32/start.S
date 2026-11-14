.section .text.start
.global _start
_start:
  j add
.global add_ret
add_ret:
  j addi
.global addi_ret
addi_ret:
  j and
.global and_ret
and_ret:
  j andi
.global andi_ret
andi_ret:
  j auipc
.global auipc_ret
auipc_ret:
  j beq
.global beq_ret
beq_ret:
  j bge
.global bge_ret
bge_ret:
  j bgeu
.global bgeu_ret
bgeu_ret:
  j blt
.global blt_ret
blt_ret:
  j bltu
.global bltu_ret
bltu_ret:
  j bne
.global bne_ret
bne_ret:
  j div
.global div_ret
div_ret:
  j divu
.global divu_ret
divu_ret:
  j j
.global j_ret
j_ret:
  j jal
.global jal_ret
jal_ret:
  j jalr
.global jalr_ret
jalr_ret:
  j lb
.global lb_ret
lb_ret:
  j lbu
.global lbu_ret
lbu_ret:
  j lh
.global lh_ret
lh_ret:
  j lhu
.global lhu_ret
lhu_ret:
  j lui
.global lui_ret
lui_ret:
  j lw
.global lw_ret
lw_ret:
  j mul
.global mul_ret
mul_ret:
  j mulh
.global mulh_ret
mulh_ret:
  j mulhsu
.global mulhsu_ret
mulhsu_ret:
  j mulhu
.global mulhu_ret
mulhu_ret:
  j or
.global or_ret
or_ret:
  j ori
.global ori_ret
ori_ret:
  j rem
.global rem_ret
rem_ret:
  j remu
.global remu_ret
remu_ret:
  j sb
.global sb_ret
sb_ret:
  j sh
.global sh_ret
sh_ret:
  j simple
.global simple_ret
simple_ret:
  j sll
.global sll_ret
sll_ret:
  j slli
.global slli_ret
slli_ret:
  j slt
.global slt_ret
slt_ret:
  j slti
.global slti_ret
slti_ret:
  j sra
.global sra_ret
sra_ret:
  j srai
.global srai_ret
srai_ret:
  j srl
.global srl_ret
srl_ret:
  j srli
.global srli_ret
srli_ret:
  j sub
.global sub_ret
sub_ret:
  j sw
.global sw_ret
sw_ret:
  j xor
.global xor_ret
xor_ret:
  j xori
.global xori_ret
xori_ret:
  li a0, 0x20000000
  li a1, 123456789
  sw a1, 0(a0)
  ebreak
