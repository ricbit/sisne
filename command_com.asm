; SISNE COMMAND.COM V3.30 R05 (03.Dez.90) — disk 1 command interpreter
; Disassembled by Ricardo Bittencourt (bluepenguin@gmail.com)
; Last update at 2026-07-29
;
        .8086
        .model tiny
        .code
        org 00100h

RESIDENT_PARAS                   equ     00252h    ; Paragraphs the resident part keeps, computed at init
VERSION_COPY                     equ     00B56h    ; 11 bytes copied out of the banner at init
VERSION_R_FLAG                   equ     00B5Dh    ; 'R' here selects the alternate terminator at 0B60h

COMMAND_ENTRY:
        ; .COM entry — jmp over the banner and the fixup table
        jmp     short COMMAND_INIT                             ;#0100: EB 4B
        nop                                                    ;#0102: 90
        db      0Dh, "COMMAND  -  V3.30  R05  -  03.Dez.90", 0Dh, 0Ah, 0Dh, 0Ah, "$" ;#0103: 0D 43 4F 4D 4D 41 4E 44 20 20 2D 20 20 56 33 2E 33 30 20 20 52 30 35 20 20 2D 20 20 30 33 2E 44 65 7A 2E 39 30 0D 0A 0D 0A 24

BANNER_TAIL:
        ; Four bytes after the banner: 08 20 08 1A
        ; Format: FORMAT_HEX
        ; raw
        db      8, 20h, 8, 1Ah                                 ;#012D

SEGMENT_FIXUP_TABLE:
        ; Words naming the segment halves COMMAND_INIT patches
        dw      293h                                           ;#0131: 93 02
        dw      297h                                           ;#0133: 97 02
        dw      29Bh                                           ;#0135: 9B 02
        dw      29Fh                                           ;#0137: 9F 02
        dw      2A3h                                           ;#0139: A3 02
        dw      266h                                           ;#013B: 66 02
        dw      26Ah                                           ;#013D: 6A 02
        dw      26Eh                                           ;#013F: 6E 02
        dw      270h                                           ;#0141: 70 02
        dw      2A9h                                           ;#0143: A9 02
        dw      2ADh                                           ;#0145: AD 02
        dw      2B1h                                           ;#0147: B1 02
        dw      283h                                           ;#0149: 83 02
        dw      0                                              ;#014B: 00 00

COMMAND_INIT:
        ; Set SP, run the fixups, stage the version bytes, jump to the body
        cli                                                    ;#014D: FA
        mov     sp, 200h                                       ;#014E: BC 00 02
        cld                                                    ;#0151: FC
        mov     si, SEGMENT_FIXUP_TABLE                        ;#0152: BE 31 01
        lodsw                                                  ;#0155: AD
        or      ax, ax                                         ;#0156: 0B C0
        jz      short FIXUP_DONE                               ;#0158: 74 06
        mov     bx, ax                                         ;#015A: 8B D8
        mov     [bx], cs                                       ;#015C: 8C 0F
        jmp     short 155h                                     ;#015E: EB F5

FIXUP_DONE:
        ; Compute the resident paragraph count into [252h]
        mov     ax, [2]                                        ;#0160: A1 02 00
        mov     bx, 4F70h                                      ;#0163: BB 70 4F
        mov     cl, 4                                          ;#0166: B1 04
        shr     bx, cl                                         ;#0168: D3 EB
        sub     ax, bx                                         ;#016A: 2B C3
        mov     [252h], ax                                     ;#016C: A3 52 02
        mov     si, 110h                                       ;#016F: BE 10 01
        mov     di, 0B56h                                      ;#0172: BF 56 0B
        mov     cx, 0Bh                                        ;#0175: B9 0B 00
        rep     movsb                                          ;#0178: F3 A4
        cmp     byte [0B5Dh], 52h                              ;#017A: 80 3E 5D 0B 52
        jnz     short 186h                                     ;#017F: 75 05
        mov     byte [0B60h], 24h                              ;#0181: C6 06 60 0B 24
        sti                                                    ;#0186: FB
        jmp     near 174Ah                                     ;#0187: E9 C0 15

HEAD_DATA:
        ; Data the fixup table points into — far pointers awaiting their segment
        ; Format: FORMAT_HEX
        ; raw
        db      0, 0, 0, 0                                     ;#018A
        db      0, 0, 28h, 46h                                 ;#018E
        db      72h, 65h, 75h, 64h                             ;#0192
        db      29h, 90h, 6Eh, 0                               ;#0196
        db      0, 0, 0, 0                                     ;#019A
        db      0, 0, 0, 0                                     ;#019E
        db      0, 0, 0, 0                                     ;#01A2
        db      0, 0, 0, 0                                     ;#01A6
        db      0, 0, 0, 0                                     ;#01AA
        db      0, 0, 0, 0                                     ;#01AE
        db      0, 0, 0, 0                                     ;#01B2
        db      0, 0, 0, 0                                     ;#01B6
        db      0, 0, 0, 0                                     ;#01BA
        db      0, 0, 0, 0                                     ;#01BE
        db      0, 0, 0, 0                                     ;#01C2
        db      0, 0, 0, 0                                     ;#01C6
        db      0, 0, 0, 0                                     ;#01CA
        db      0, 0, 0, 0                                     ;#01CE
        db      0, 0, 0, 0                                     ;#01D2
        db      0, 0, 0, 0                                     ;#01D6
        db      0, 0, 0, 0                                     ;#01DA
        db      0, 0, 0, 0                                     ;#01DE
        db      0, 0, 0, 0                                     ;#01E2
        db      0, 0, 0, 0                                     ;#01E6
        db      0, 0, 0, 0                                     ;#01EA
        db      0, 0, 0, 0                                     ;#01EE
        db      0, 0, 0, 0                                     ;#01F2
        db      0, 0, 0, 0                                     ;#01F6
        db      0, 0, 0, 0                                     ;#01FA
        db      0, 0, 0, 0                                     ;#01FE
        db      0, 0, 0, 0                                     ;#0202
        db      0, 0, 0, 0                                     ;#0206
        db      0, 0, 0, 0                                     ;#020A
        db      0, 0, 0, 0                                     ;#020E
        db      0, 0, 0, 0                                     ;#0212
        db      0, 0, 0, 0                                     ;#0216
        db      0, 0, 0, 0                                     ;#021A
        db      0, 0, 0, 0                                     ;#021E
        db      0, 0, 0, 0                                     ;#0222
        db      0, 0, 0, 0                                     ;#0226
        db      0, 0, 0, 0                                     ;#022A
        db      0, 0, 0, 0                                     ;#022E
        db      0, 0, 0, 0                                     ;#0232
        db      0, 0, 0, 0                                     ;#0236
        db      0, 0, 0, 0                                     ;#023A
        db      0, 0, 0, 0                                     ;#023E
        db      0, 0, 0, 0                                     ;#0242
        db      0, 0, 0, 0                                     ;#0246
        db      0, 0, 0, 0                                     ;#024A
        db      0, 0                                           ;#024E
        cmp     cl, [0]                                        ;#0250: 3A 0E 00 00
        db      16 dup (0)
        cwd                                                    ;#0264: 99
        push    cs                                             ;#0265: 0E
        add     [bx+si], al                                    ;#0266: 00 00
        or      word [bx], 0                                   ;#0268: 81 0F 00 00
        in      ax, 0Fh                                        ;#026C: E5 0F
        db      10 dup (0)
        add     [bx+di], ax                                    ;#0278: 01 01
        inc     word [bx+si]                                   ;#027A: FF 00
        add     [bx+si], al                                    ;#027C: 00 00
        add     [bx+si], al                                    ;#027E: 00 00
        add     [bx+si+0Fh], bl                                ;#0280: 00 98 0F 00
        add     ch, ch                                         ;#0284: 00 ED
        db      0Fh                                            ;#0286: 0F
        db      10 dup (0)
        cwd                                                    ;#0291: 99
        push    cs                                             ;#0292: 0E
        add     [bx+si], al                                    ;#0293: 00 00
        sbb     [bx], cx                                       ;#0295: 19 0F
        add     [bx+si], al                                    ;#0297: 00 00
        db      62h                                            ;#0299: 62
        adc     [bx+si], ax                                    ;#029A: 11 00
        add     [bp+11h], ah                                   ;#029C: 00 66 11
        add     [bx+si], al                                    ;#029F: 00 00
        xor     dl, [bx+di]                                    ;#02A1: 32 11
        add     [bx+si], al                                    ;#02A3: 00 00
        add     [bx+si], al                                    ;#02A5: 00 00
        add     byte [bx+si], 0                                ;#02A7: 80 00 00
        add     [si], bl                                       ;#02AA: 00 5C 00
        add     [bx+si], al                                    ;#02AD: 00 00
        db      6Ch                                            ;#02AF: 6C
        add     [bx+si], al                                    ;#02B0: 00 00
        add     [bx+si+0D00h], al                              ;#02B2: 00 80 00 0D
        db      133 dup (0)
        db      0FFh                                           ;#033B: FF
        inc     word [bx+si]                                   ;#033C: FF 00
        db      160 dup (0)
        add     [bx+si], ax                                    ;#03DE: 01 00
        add     [bx+si], al                                    ;#03E0: 00 00
        db      0                                              ;#03E2: 00

AUTOEXEC_PATH:
        ; ' :\AUTOEXEC.BAT' — the leading blank takes the boot drive letter
        ; Format: FORMAT_STRING
        db      " :", 5Ch, "AUTOEXEC.BAT", 0                   ;#03E3: 20 3A 5C 41 55 54 4F 45 58 45 43 2E 42 41 54 00
        db      213 dup (0)

PIPE_NAME_PTRS:
        ; Two words: pointers to the second and first pipe temp names
        dw      PIPE_TEMP_NAME_2                               ;#04C8: DC 04
        dw      PIPE_TEMP_NAME_1                               ;#04CA: CC 04

PIPE_TEMP_NAME_1:
        ; ' :\PIPEARQ1.TMP' — first pipe spill file, drive letter patched in
        ; Format: FORMAT_STRING
        db      " :", 5Ch, "PIPEARQ1.TMP", 0                   ;#04CC: 20 3A 5C 50 49 50 45 41 52 51 31 2E 54 4D 50 00

PIPE_TEMP_NAME_2:
        ; ' :\PIPEARQ2.TMP' — second pipe spill file
        ; Format: FORMAT_STRING
        db      " :", 5Ch, "PIPEARQ2.TMP", 0                   ;#04DC: 20 3A 5C 50 49 50 45 41 52 51 32 2E 54 4D 50 00
        db      317 dup (0)
        db      0D4h                                           ;#0629: D4

MSG_PROTEGIDO:
        ; " protegido."
        ; Format: FORMAT_STRING
        db      " protegido", 0FFh                             ;#062A: 20 70 72 6F 74 65 67 69 64 6F FF

MSG_UNIDADE:
        ; "Unidade"
        ; Format: FORMAT_STRING
        db      "Unidade"                                      ;#0635: 55 6E 69 64 61 64 65
        sar     di, cl                                         ;#063C: D3 FF
        db      0D4h                                           ;#063E: D4

MSG_OU_DISPOSITIVO_AUSENTE:
        ; " ou dispositivo ausente"
        ; Format: FORMAT_STRING
        db      " ou dispositivo ausente"                      ;#063F: 20 6F 75 20 64 69 73 70 6F 73 69 74 69 76 6F 20 61 75 73 65 6E 74 65
        call    dx                                             ;#0656: FF D2
        db      0C7h                                           ;#0658: C7
        db      0FFh                                           ;#0659: FF

MSG_SETOR_RUIM:
        ; "Setor ruim."
        ; Format: FORMAT_STRING
        db      "Setor ruim", 0FFh                             ;#065A: 53 65 74 6F 72 20 72 75 69 6D FF

MSG_ESTRUTURA:
        ; "Estrutura.."
        ; Format: FORMAT_STRING
        db      "Estrutura", 0D3h, 0FFh                        ;#0665: 45 73 74 72 75 74 75 72 61 D3 FF

MSG_TRILHA_NAO_ENCONTRADA:
        ; "Trilha não encontrada."
        ; Format: FORMAT_STRING
        db      "Trilha não encontrada", 0FFh                  ;#0670: 54 72 69 6C 68 61 20 6E 84 6F 20 65 6E 63 6F 6E 74 72 61 64 61 FF

MSG_FORMATACAO_DESCONHECIDA:
        ; "Formatação desconhecida."
        ; Format: FORMAT_STRING
        db      "Formatação desconhecida", 0FFh                ;#0686: 46 6F 72 6D 61 74 61 87 84 6F 20 64 65 73 63 6F 6E 68 65 63 69 64 61 FF

MSG_SETOR_NAO_ENCONTRADO:
        ; "Setor não encontrado."
        ; Format: FORMAT_STRING
        db      "Setor não encontrado", 0FFh                   ;#069E: 53 65 74 6F 72 20 6E 84 6F 20 65 6E 63 6F 6E 74 72 61 64 6F FF

MSG_IMPRESSORA_SEM_PAPEL:
        ; "Impressora sem papel."
        ; Format: FORMAT_STRING
        db      "Impressora sem papel", 0FFh                   ;#06B3: 49 6D 70 72 65 73 73 6F 72 61 20 73 65 6D 20 70 61 70 65 6C FF

MSG_FALHA_NO_ACESSO:
        ; "Falha no acesso"
        ; Format: FORMAT_STRING
        db      "Falha no acesso"                              ;#06C8: 46 61 6C 68 61 20 6E 6F 20 61 63 65 73 73 6F
        db      0FFh                                           ;#06D7: FF
        db      0BAh                                           ;#06D8: BA
        db      0FFh                                           ;#06D9: FF

MSG_PROBLEMA_DETECTADO:
        ; "Problema detectado"
        ; Format: FORMAT_STRING
        db      "Problema detectado"                           ;#06DA: 50 72 6F 62 6C 65 6D 61 20 64 65 74 65 63 74 61 64 6F
        call    si                                             ;#06EC: FF D6
        xlatb                                                  ;#06EE: D7
        call    si                                             ;#06EF: FF D6

MSG_DE_REGIAO_BLOQUEADA:
        ; " de região bloqueada."
        ; Format: FORMAT_STRING
        db      " de região bloqueada", 0FFh                   ;#06F1: 20 64 65 20 72 65 67 69 84 6F 20 62 6C 6F 71 75 65 61 64 61 FF

MSG_TROCA_DE_DISCO:
        ; "Troca. de disco."
        ; Format: FORMAT_STRING
        db      "Troca", 0D3h, " de disco", 0FFh               ;#0706: 54 72 6F 63 61 D3 20 64 65 20 64 69 73 63 6F FF

MSG_FCB_NAO_DISPONIVEL:
        ; "FCB não disponível."
        ; Format: FORMAT_STRING
        db      "FCB não disponível", 0FFh                     ;#0716: 46 43 42 20 6E 84 6F 20 64 69 73 70 6F 6E A1 76 65 6C FF

MSG_ESTOURO_NO_BUFFER:
        ; "Estouro no buffer.."
        ; Format: FORMAT_STRING
        db      "Estouro no buffer", 0D7h, 0FFh                ;#0729: 45 73 74 6F 75 72 6F 20 6E 6F 20 62 75 66 66 65 72 D7 FF

MSG_REQUISICAO_NAO_SUPORTADA_PELA:
        ; "Requisição não suportada pela rede."
        ; Format: FORMAT_STRING
        db      "Requisição não suportada pela rede", 0FFh     ;#073C: 52 65 71 75 69 73 69 87 84 6F 20 6E 84 6F 20 73 75 70 6F 72 74 61 64 61 20 70 65 6C 61 20 72 65 64 65 FF

MSG_ARQUIVO:
        ; " arquivo."
        ; Format: FORMAT_STRING
        db      " arquivo", 0FFh                               ;#075F: 20 61 72 71 75 69 76 6F FF

MSG_MEMORIA:
        ; "Memória."
        ; Format: FORMAT_STRING
        db      "Memória", 0FFh                                ;#0768: 4D 65 6D A2 72 69 61 FF

MSG_COMMAND_COM:
        ; "COMMAND.COM."
        ; Format: FORMAT_STRING
        db      "COMMAND.COM", 0FFh                            ;#0770: 43 4F 4D 4D 41 4E 44 2E 43 4F 4D FF

MSG_CANCELAR:
        ; "Cancelar."
        ; Format: FORMAT_STRING
        db      "Cancelar", 0FFh                               ;#077C: 43 61 6E 63 65 6C 61 72 FF

MSG_INVALIDO:
        ; " inválido."
        ; Format: FORMAT_STRING
        db      " inválido", 0FFh                              ;#0785: 20 69 6E 76 A0 6C 69 64 6F FF

MSG_UNIDADE_2:
        ; " unidade ."
        ; Format: FORMAT_STRING
        db      " unidade ", 0FFh                              ;#078F: 20 75 6E 69 64 61 64 65 20 FF

MSG_IMPOSSIVEL:
        ; "Impossível ."
        ; Format: FORMAT_STRING
        db      "Impossível ", 0FFh                            ;#0799: 49 6D 70 6F 73 73 A1 76 65 6C 20 FF

MSG_CARREGAR:
        ; "carregar ."
        ; Format: FORMAT_STRING
        db      "carregar ", 0FFh                              ;#07A5: 63 61 72 72 65 67 61 72 20 FF

MSG_PADRAO:
        ; "padrão."
        ; Format: FORMAT_STRING
        db      "padrão", 0FFh                                 ;#07AF: 70 61 64 72 84 6F FF

MSG_EXCEDIDO_LIMITE_DE_ABERTOS:
        ; "Excedido o limite de.s abertos."
        ; Format: FORMAT_STRING
        db      "Excedido o limite de", 0C3h, "s abertos", 0FFh ;#07B6: 45 78 63 65 64 69 64 6F 20 6F 20 6C 69 6D 69 74 65 20 64 65 C3 73 20 61 62 65 72 74 6F 73 FF

MSG_INSUFICIENTE:
        ; " insuficiente.."
        ; Format: FORMAT_STRING
        db      " insuficiente", 0FFh, 0FFh                    ;#07D5: 20 69 6E 73 75 66 69 63 69 65 6E 74 65 FF FF

MSG_PERSISTIR:
        ; ", Persistir."
        ; Format: FORMAT_STRING
        db      ", Persistir", 0FFh                            ;#07E4: 2C 20 50 65 72 73 69 73 74 69 72 FF

MSG_IGNORAR:
        ; ", Ignorar."
        ; Format: FORMAT_STRING
        db      ", Ignorar", 0FFh                              ;#07F0: 2C 20 49 67 6E 6F 72 61 72 FF

MSG_FALHAR:
        ; ", Falhar."
        ; Format: FORMAT_STRING
        db      ", Falhar", 0FFh                               ;#07FA: 2C 20 46 61 6C 68 61 72 FF

MSG_COMANDO:
        ; "Comando."
        ; Format: FORMAT_STRING
        db      "Comando", 0FFh                                ;#0803: 43 6F 6D 61 6E 64 6F FF

MSG_INVALIDA:
        ; " inválida."
        ; Format: FORMAT_STRING
        db      " inválida", 0FFh                              ;#080B: 20 69 6E 76 A0 6C 69 64 61 FF

MSG_DISCO:
        ; "Disco"
        ; Format: FORMAT_STRING
        db      "Disco"                                        ;#0815: 44 69 73 63 6F
        dec     word [di]                                      ;#081A: FF 0D
        or      bh, bh                                         ;#081C: 0A FF

MSG_VIOLACAO:
        ; "Violação."
        ; Format: FORMAT_STRING
        db      "Violação", 0FFh                               ;#081E: 56 69 6F 6C 61 87 84 6F FF

MSG_DE_COMPARTILHAMENTO:
        ; " de compartilhamento."
        ; Format: FORMAT_STRING
        db      " de compartilhamento", 0FFh                   ;#0827: 20 64 65 20 63 6F 6D 70 61 72 74 69 6C 68 61 6D 65 6E 74 6F FF

MSG_ERRO:
        ; "Erro ."
        ; Format: FORMAT_STRING
        db      "Erro ", 0FFh                                  ;#083C: 45 72 72 6F 20 FF

MSG_LEITURA:
        ; "leitura."
        ; Format: FORMAT_STRING
        db      "leitura", 0FFh                                ;#0842: 6C 65 69 74 75 72 61 FF

MSG_ESCRITA:
        ; "escrita"
        ; Format: FORMAT_STRING
        db      "escrita"                                      ;#084A: 65 73 63 72 69 74 61
        jmp     word [bx+si]                                   ;#0851: FF 20
        db      6Eh                                            ;#0853: 6E
        db      61h                                            ;#0854: 61
        db      0C8h                                           ;#0855: C8
        and     [bp+si], bh                                    ;#0856: 20 3A
        db      0FFh                                           ;#0858: FF

MSG_NO_DISPOSITIVO:
        ; " no dispositivo         "
        ; Format: FORMAT_STRING
        db      " no dispositivo         "                     ;#0859: 20 6E 6F 20 64 69 73 70 6F 73 69 74 69 76 6F 20 20 20 20 20 20 20 20 20
        jmp     word [bx+si]                                   ;#0871: FF 20
        and     [bx+0AFAFh], ch                                ;#0873: 20 AF AF AF
        and     bh, bh                                         ;#0877: 20 FF
        and     [bx+si], ah                                    ;#0879: 20 20
        jmp     dx                                             ;#087B: FF E2

MSG_DANIFICADA:
        ; " danificada."
        ; Format: FORMAT_STRING
        db      " danificada", 0FFh                            ;#087D: 20 64 61 6E 69 66 69 63 61 64 61 FF

MSG_AREA_AFETADA:
        ; ".área afetada: "
        ; Format: FORMAT_STRING
        db      0DEh, "área afetada: "                         ;#0889: DE A0 72 65 61 20 61 66 65 74 61 64 61 3A 20
        add     [0FFD5h], ch                                   ;#0898: 00 2E D5 FF

MSG_SISTEMA:
        ; "Sistema."
        ; Format: FORMAT_STRING
        db      "Sistema", 0FFh                                ;#089C: 53 69 73 74 65 6D 61 FF

MSG_TABELA_DE_ALOCACAO_FAT:
        ; "Tabela de alocação (FAT)."
        ; Format: FORMAT_STRING
        db      "Tabela de alocação (FAT)", 0FFh               ;#08A4: 54 61 62 65 6C 61 20 64 65 20 61 6C 6F 63 61 87 84 6F 20 28 46 41 54 29 FF

MSG_DIRETORIO:
        ; "Diretório."
        ; Format: FORMAT_STRING
        db      "Diretório", 0FFh                              ;#08BD: 44 69 72 65 74 A2 72 69 6F FF

MSG_DADOS:
        ; "Dados."
        ; Format: FORMAT_STRING
        db      "Dados", 0FFh                                  ;#08C7: 44 61 64 6F 73 FF

MSG_COLOQUE_DISCO_CORRETO:
        ; ".Coloque o disco correto    .."
        ; Format: FORMAT_STRING
        db      0DEh, "Coloque o disco correto    ", 0D5h, 0FFh ;#08CD: DE 43 6F 6C 6F 71 75 65 20 6F 20 64 69 73 63 6F 20 63 6F 72 72 65 74 6F 20 20 20 20 D5 FF

MSG_NA_CARGA_DO:
        ; "na carga do ."
        ; Format: FORMAT_STRING
        db      "na carga do ", 0FFh                           ;#08EB: 6E 61 20 63 61 72 67 61 20 64 6F 20 FF

MSG_COMANDO_2:
        ; "comando"
        ; Format: FORMAT_STRING
        db      "comando"                                      ;#08F8: 63 6F 6D 61 6E 64 6F
        jmp     far word [bx+di]                               ;#08FF: FF 29
        push    es                                             ;#0901: 06
        xor     ax, 3E06h                                      ;#0902: 35 06 3E
        push    es                                             ;#0905: 06
        push    di                                             ;#0906: 57
        push    es                                             ;#0907: 06
        pop     dx                                             ;#0908: 5A
        push    es                                             ;#0909: 06
        db      65h                                            ;#090A: 65
        push    es                                             ;#090B: 06
        jo      short 914h                                     ;#090C: 70 06
        xchg    [MSG_SETOR_NAO_ENCONTRADO], al                 ;#090E: 86 06 9E 06
        mov     bl, 6                                          ;#0912: B3 06
        db      0C8h                                           ;#0914: C8
        push    es                                             ;#0915: 06
        db      0D8h                                           ;#0916: D8
        push    es                                             ;#0917: 06
        db      0DAh                                           ;#0918: DA
        push    es                                             ;#0919: 06
        in      ax, dx                                         ;#091A: ED
        push    es                                             ;#091B: 06
        lock    push es                                        ;#091C: F0 06
        push    es                                             ;#091E: 06
        pop     es                                             ;#091F: 07
        push    ss                                             ;#0920: 16
        pop     es                                             ;#0921: 07
        sub     [bx], ax                                       ;#0922: 29 07
        cmp     al, 7                                          ;#0924: 3C 07
        pop     di                                             ;#0926: 5F
        pop     es                                             ;#0927: 07
        db      68h                                            ;#0928: 68
        pop     es                                             ;#0929: 07
        jo      short 933h                                     ;#092A: 70 07
        jl      short 935h                                     ;#092C: 7C 07
        test    [bx], ax                                       ;#092E: 85 07
        pop     word [bx]                                      ;#0930: 8F 07
        cwd                                                    ;#0932: 99
        pop     es                                             ;#0933: 07
        movsw                                                  ;#0934: A5
        pop     es                                             ;#0935: 07
        scasw                                                  ;#0936: AF
        pop     es                                             ;#0937: 07
        mov     dh, 7                                          ;#0938: B6 07
        aad     7                                              ;#093A: D5 07
        jcxz    945h                                           ;#093C: E3 07
        in      al, 7                                          ;#093E: E4 07
        lock    pop es                                         ;#0940: F0 07
        cli                                                    ;#0942: FA
        pop     es                                             ;#0943: 07
        add     cx, [bx+si]                                    ;#0944: 03 08
        or      cx, [bx+si]                                    ;#0946: 0B 08
        adc     ax, 1B08h                                      ;#0948: 15 08 1B
        or      [2708h], bl                                    ;#094B: 08 1E 08 27
        or      [si], bh                                       ;#094F: 08 3C
        or      [bp+si+8], al                                  ;#0951: 08 42 08
        dec     dx                                             ;#0954: 4A
        or      [bp+si+8], dl                                  ;#0955: 08 52 08
        pop     cx                                             ;#0958: 59
        or      [bp+si+8], dh                                  ;#0959: 08 72 08
        jns     short 966h                                     ;#095C: 79 08
        jl      short 968h                                     ;#095E: 7C 08
        mov     [bx+si], cx                                    ;#0960: 89 08
        pushf                                                  ;#0962: 9C
        or      [si+0BD08h], ah                                ;#0963: 08 A4 08 BD
        or      bh, al                                         ;#0967: 08 C7
        or      ch, cl                                         ;#0969: 08 CD
        or      bl, ch                                         ;#096B: 08 EB
        or      al, bh                                         ;#096D: 08 F8
        or      dh, bl                                         ;#096F: 08 DE
        mov     bl, 20h                                        ;#0971: C6 C3 20
        db      64h                                            ;#0974: 64
        db      65h                                            ;#0975: 65
        and     bh, ah                                         ;#0976: 20 E7

MSG_0978:
        ; "s ?  (S/N): "
        ; Format: FORMAT_STRING
        db      "s ?  (S/N): "                                 ;#0978: 73 20 3F 20 20 28 53 2F 4E 29 3A 20
        call    bp                                             ;#0984: FF D5
        db      0DDh                                           ;#0986: DD
        add     [0D507h], ch                                   ;#0987: 00 2E 07 D5
        db      0DEh                                           ;#098B: DE
        db      0D8h                                           ;#098C: D8
        db      64h                                            ;#098D: 64
        db      65h                                            ;#098E: 65
        and     [bx+si], al                                    ;#098F: 20 00
        add     ch, dl                                         ;#0991: 00 D5
        into                                                   ;#0993: CE
        into                                                   ;#0994: CE
        db      0FFh                                           ;#0995: FF
        db      0DEh                                           ;#0996: DE
        db      0C6h                                           ;#0997: C6
        iret                                                   ;#0998: CF
        rcl     cl, 1                                          ;#0999: D0 D1
        and     [bx], bh                                       ;#099B: 20 3F
        and     bh, bh                                         ;#099D: 20 FF
        inc     bx                                             ;#099F: 43
        push    ax                                             ;#09A0: 50
        dec     cx                                             ;#09A1: 49
        inc     si                                             ;#09A2: 46
        db      0DEh                                           ;#09A3: DE
        db      0C6h                                           ;#09A4: C6
        iret                                                   ;#09A5: CF
        rcl     cl, 1                                          ;#09A6: D0 D1
        and     [bx], bh                                       ;#09A8: 20 3F
        and     bh, bh                                         ;#09AA: 20 FF
        inc     bx                                             ;#09AC: 43
        push    ax                                             ;#09AD: 50
        dec     cx                                             ;#09AE: 49
        inc     si                                             ;#09AF: 46
        aad     0DDh                                           ;#09B0: D5 DD
        les     cx, bp                                         ;#09B2: C4 CD

MSG_PARA:
        ; " para "
        ; Format: FORMAT_STRING
        db      " para "                                       ;#09B4: 20 70 61 72 61 20
        retf    2EC5h                                          ;#09BA: CA C5 2E
        pop     es                                             ;#09BD: 07
        call    bp                                             ;#09BE: FF D5
        db      0DDh                                           ;#09C0: DD
        db      0D8h                                           ;#09C1: D8

MSG_NA_ALOCACAO_DE:
        ; "na alocação de "
        ; Format: FORMAT_STRING
        db      "na alocação de "                              ;#09C2: 6E 61 20 61 6C 6F 63 61 87 84 6F 20 64 65 20
        les     bp, [0FF07h]                                   ;#09D1: C4 2E 07 FF
        aad     0DDh                                           ;#09D5: D5 DD
        int3                                                   ;#09D7: CC
        pop     es                                             ;#09D8: 2E 07
        call    bp                                             ;#09DA: FF D5
        db      0DDh                                           ;#09DC: DD
        db      0C5h                                           ;#09DD: C5

MSG_NAO_ENCONTRADO_OU_DEFEITUOSO:
        ; " não encontrado ou defeituoso.."
        ; Format: FORMAT_STRING
        db      " não encontrado ou defeituoso.", 7            ;#09DE: 20 6E 84 6F 20 65 6E 63 6F 6E 74 72 61 64 6F 20 6F 75 20 64 65 66 65 69 74 75 6F 73 6F 2E 07
        call    bp                                             ;#09FD: FF D5
        db      0DDh                                           ;#09FF: DD
        lds     ax, di                                         ;#0A00: C5 C7

MSG_OU_INCONSISTENTE:
        ; " ou inconsistente.."
        ; Format: FORMAT_STRING
        db      " ou inconsistente.", 7                        ;#0A02: 20 6F 75 20 69 6E 63 6F 6E 73 69 73 74 65 6E 74 65 2E 07
        call    bp                                             ;#0A15: FF D5
        db      0DEh                                           ;#0A17: DE

MSG_COLOQUE:
        ; "Coloque o "
        ; Format: FORMAT_STRING
        db      "Coloque o "                                   ;#0A18: 43 6F 6C 6F 71 75 65 20 6F 20
        lds     sp, [bx+si]                                    ;#0A22: C5 20
        db      6Eh                                            ;#0A24: 6E
        db      61h                                            ;#0A25: 61
        db      0C8h                                           ;#0A26: C8
        retf                                                   ;#0A27: CB
        into                                                   ;#0A28: CE
        aad     0DEh                                           ;#0A29: D5 DE

MSG_DIGITE_UMA_TECLA_PARA:
        ; "Digite uma tecla para continuar "
        ; Format: FORMAT_STRING
        db      "Digite uma tecla para continuar "             ;#0A2B: 44 69 67 69 74 65 20 75 6D 61 20 74 65 63 6C 61 20 70 61 72 61 20 63 6F 6E 74 69 6E 75 61 72 20
        call    bp                                             ;#0A4B: FF D5
        db      0DEh                                           ;#0A4D: DE
        db      0C9h                                           ;#0A4E: C9
        db      0CAh                                           ;#0A4F: CA
        db      0C5h                                           ;#0A50: C5

MSG_RECARREGUE_SISTEMA:
        ; ", recarregue o sistema. "
        ; Format: FORMAT_STRING
        db      ", recarregue o sistema. "                     ;#0A51: 2C 20 72 65 63 61 72 72 65 67 75 65 20 6F 20 73 69 73 74 65 6D 61 2E 20
        call    bp                                             ;#0A69: FF D5
        db      0DEh                                           ;#0A6B: DE
        db      0C9h                                           ;#0A6C: C9

MSG_ATIVAR_EXIT:
        ; "ativar ., EXIT ..."
        ; Format: FORMAT_STRING
        db      "ativar ", 0C5h, ", EXIT ..."                  ;#0A6D: 61 74 69 76 61 72 20 C5 2C 20 45 58 49 54 20 2E 2E 2E
        aad     0FFh                                           ;#0A7F: D5 FF
        aad     0DDh                                           ;#0A81: D5 DD
        les     cx, bp                                         ;#0A83: C4 CD

MSG_PARA_ATIVAR_VIA_INT:
        ; " para ativar . via INT 2EH.."
        ; Format: FORMAT_STRING
        db      " para ativar ", 0C5h, " via INT 2EH.", 7      ;#0A85: 20 70 61 72 61 20 61 74 69 76 61 72 20 C5 20 76 69 61 20 49 4E 54 20 32 45 48 2E 07
        aad     0FFh                                           ;#0AA1: D5 FF
        db      0DDh                                           ;#0AA3: DD
        rol     bh, cl                                         ;#0AA4: D2 C7
        pop     es                                             ;#0AA6: 2E 07
        aad     0FFh                                           ;#0AA8: D5 FF
        db      0DDh                                           ;#0AAA: DD
        int3                                                   ;#0AAB: CC
        pop     es                                             ;#0AAC: 2E 07
        aad     0FFh                                           ;#0AAE: D5 FF
        db      0DDh                                           ;#0AB0: DD

MSG_ACESSO_AO_REJEITADO:
        ; "Acesso ao . rejeitado.."
        ; Format: FORMAT_STRING
        db      "Acesso ao ", 0E7h, " rejeitado.", 7           ;#0AB1: 41 63 65 73 73 6F 20 61 6F 20 E7 20 72 65 6A 65 69 74 61 64 6F 2E 07
        aad     0FFh                                           ;#0AC8: D5 FF
        db      0DDh                                           ;#0ACA: DD
        les     cx, bp                                         ;#0ACB: C4 CD

MSG_PARA_2:
        ; " para "
        ; Format: FORMAT_STRING
        db      " para "                                       ;#0ACD: 20 70 61 72 61 20
        retf    206Fh                                          ;#0AD3: CA 6F 20
        out     2Eh, ax                                        ;#0AD6: E7 2E
        pop     es                                             ;#0AD8: 07
        aad     0FFh                                           ;#0AD9: D5 FF
        db      0DDh                                           ;#0ADB: DD

MSG_CONTEXTO:
        ; "Contexto"
        ; Format: FORMAT_STRING
        db      "Contexto"                                     ;#0ADC: 43 6F 6E 74 65 78 74 6F
        db      0C7h                                           ;#0AE4: C7
        and     dh, ah                                         ;#0AE5: 20 E6
        out     2Eh, ax                                        ;#0AE7: E7 2E
        pop     es                                             ;#0AE9: 07
        aad     0FFh                                           ;#0AEA: D5 FF
        db      0DDh                                           ;#0AEC: DD

MSG_FORMATO:
        ; "Formato"
        ; Format: FORMAT_STRING
        db      "Formato"                                      ;#0AED: 46 6F 72 6D 61 74 6F
        db      0C7h                                           ;#0AF4: C7
        and     [si+6Fh], ah                                   ;#0AF5: 20 64 6F
        ret                                                    ;#0AF8: C3

MSG_EXE:
        ; " ".EXE".."
        ; Format: FORMAT_STRING
        db      " ", 22h, ".EXE", 22h, ".", 7                  ;#0AF9: 20 22 2E 45 58 45 22 2E 07
        aad     0FFh                                           ;#0B02: D5 FF
        db      0DDh                                           ;#0B04: DD
        db      0D8h                                           ;#0B05: D8
        out     0E7h, al                                       ;#0B06: E6 E7
        pop     es                                             ;#0B08: 2E 07
        aad     0FFh                                           ;#0B0A: D5 FF
        add     al, 0Bh                                        ;#0B0C: 04 0B
        add     al, 0Bh                                        ;#0B0E: 04 0B
        mov     [40Ah], ax                                     ;#0B10: A3 0A 04
        or      bp, [bp+si+0B00Ah]                             ;#0B13: 0B AA 0A B0
        or      al, [si]                                       ;#0B17: 0A 04
        or      cx, dx                                         ;#0B19: 0B CA
        or      cl, dl                                         ;#0B1B: 0A CA
        or      al, [si]                                       ;#0B1D: 0A 04
        or      bx, bx                                         ;#0B1F: 0B DB
        or      ch, ah                                         ;#0B21: 0A EC
        or      al, [si]                                       ;#0B23: 0A 04
        db      0Bh                                            ;#0B25: 0B

MSG_SISNE_PLUS:
        ; "  SISNE Plus  V0.00  R00$$"
        ; Format: FORMAT_STRING
        db      "  SISNE Plus  V0.00  R00$$"                   ;#0B26: 20 20 53 49 53 4E 45 20 50 6C 75 73 20 20 56 30 2E 30 30 20 20 52 30 30 24 24

MSG_COMSPEC_COMMAND_PRV:
        ; "COMSPEC=  COMMAND     V0.00  R00$$PRV"
        ; Format: FORMAT_STRING
        db      "COMSPEC=  COMMAND     V0.00  R00$$PRV"        ;#0B40: 43 4F 4D 53 50 45 43 3D 20 20 43 4F 4D 4D 41 4E 44 20 20 20 20 20 56 30 2E 30 30 20 20 52 30 30 24 24 50 52 56
        mov     si, 264h                                       ;#0B65: BE 64 02
        lds     dx, [si]                                       ;#0B68: C5 14
        mov     ax, 2522h                                      ;#0B6A: B8 22 25
        int     21h                                            ;#0B6D: CD 21
        lds     dx, [si+4]                                     ;#0B6F: C5 54 04
        inc     al                                             ;#0B72: FE C0
        int     21h                                            ;#0B74: CD 21
        lds     dx, [si+8]                                     ;#0B76: C5 54 08
        inc     al                                             ;#0B79: FE C0
        int     21h                                            ;#0B7B: CD 21
        pop     si                                             ;#0B7D: 5E
        pop     dx                                             ;#0B7E: 5A
        pop     ax                                             ;#0B7F: 58
        ret                                                    ;#0B80: C3
        push    dx                                             ;#0B81: 52
        mov     ax, 3700h                                      ;#0B82: B8 00 37
        int     21h                                            ;#0B85: CD 21
        mov     ax, dx                                         ;#0B87: 8B C2
        pop     dx                                             ;#0B89: 5A
        mov     ah, 2Fh                                        ;#0B8A: B4 2F
        cmp     al, ah                                         ;#0B8C: 3A C4
        jnz     short 0B92h                                    ;#0B8E: 75 02
        mov     ah, 5Ch                                        ;#0B90: B4 5C
        ret                                                    ;#0B92: C3
        push    ds                                             ;#0B93: 1E
        mov     ds, [252h]                                     ;#0B94: 8E 1E 52 02
        push    si                                             ;#0B98: 56
        push    cx                                             ;#0B99: 51
        mov     si, COMMAND_ENTRY                              ;#0B9A: BE 00 01
        mov     cx, 4660h                                      ;#0B9D: B9 60 46
        sub     cx, si                                         ;#0BA0: 2B CE
        shr     cx, 1                                          ;#0BA2: D1 E9
        push    bx                                             ;#0BA4: 53
        xor     bx, bx                                         ;#0BA5: 33 DB
        lodsw                                                  ;#0BA7: AD
        add     bx, ax                                         ;#0BA8: 03 D8
        loop    0BA7h                                          ;#0BAA: E2 FB
        mov     ax, bx                                         ;#0BAC: 8B C3
        pop     bx                                             ;#0BAE: 5B
        pop     cx                                             ;#0BAF: 59
        pop     si                                             ;#0BB0: 5E
        pop     ds                                             ;#0BB1: 1F
        cmp     ax, [254h]                                     ;#0BB2: 3B 06 54 02
        ret                                                    ;#0BB6: C3
        call    near 0E44h                                     ;#0BB7: E8 8A 02
        call    near 0D32h                                     ;#0BBA: E8 75 01
        call    near 0BC6h                                     ;#0BBD: E8 06 00
        call    near MSG_PS                                    ;#0BC0: E8 98 01
        jmp     near 0E41h                                     ;#0BC3: E9 7B 02
        push    dx                                             ;#0BC6: 52
        mov     ax, 0C07h                                      ;#0BC7: B8 07 0C
        int     21h                                            ;#0BCA: CD 21
        push    ax                                             ;#0BCC: 50
        mov     dl, al                                         ;#0BCD: 8A D0

MSG_0BCF:
        ; ", <_s"
        ; Format: FORMAT_STRING
        db      ", <_s"                                        ;#0BCF: 2C 20 3C 5F 73
        add     al, 0B4h                                       ;#0BD4: 04 B4
        add     cl, ch                                         ;#0BD6: 02 CD
        and     [bx+si+0C00h], di                              ;#0BD8: 21 B8 00 0C
        int     21h                                            ;#0BDC: CD 21
        pop     ax                                             ;#0BDE: 58
        call    near 0BE4h                                     ;#0BDF: E8 02 00
        pop     dx                                             ;#0BE2: 5A
        ret                                                    ;#0BE3: C3
        cmp     al, 61h                                        ;#0BE4: 3C 61
        jb      short 0BEEh                                    ;#0BE6: 72 06
        cmp     al, 7Ah                                        ;#0BE8: 3C 7A
        jnbe    short 0BEEh                                    ;#0BEA: 77 02
        sub     al, 20h                                        ;#0BEC: 2C 20
        ret                                                    ;#0BEE: C3
        mov     cl, 0FFh                                       ;#0BEF: B1 FF
        xchg    [si], cl                                       ;#0BF1: 86 0C
        cmp     cl, 0FFh                                       ;#0BF3: 80 F9 FF
        jz      short 0BFFh                                    ;#0BF6: 74 07
        mov     ah, 3Eh                                        ;#0BF8: B4 3E
        int     21h                                            ;#0BFA: CD 21
        mov     [bx+18h], cl                                   ;#0BFC: 88 4F 18
        ret                                                    ;#0BFF: C3
        cli                                                    ;#0C00: FA
        xor     ax, ax                                         ;#0C01: 33 C0
        mov     ds, ax                                         ;#0C03: 8E D8
        mov     bx, 8Ch                                        ;#0C05: BB 8C 00
        mov     ax, [bx]                                       ;#0C08: 8B 07
        xchg    [cs:281h], ax                                  ;#0C0A: 2E 87 06 81 02
        mov     [bx], ax                                       ;#0C0F: 89 07
        mov     ax, [bx+2]                                     ;#0C11: 8B 47 02
        xchg    [cs:283h], ax                                  ;#0C14: 2E 87 06 83 02
        mov     [bx+2], ax                                     ;#0C19: 89 47 02
        sti                                                    ;#0C1C: FB
        ret                                                    ;#0C1D: C3
        mov     dx, 101h                                       ;#0C1E: BA 01 01
        push    ax                                             ;#0C21: 50
        not     dx                                             ;#0C22: F7 D2
        and     dx, 101h                                       ;#0C24: 81 E2 01 01
        mov     ax, 180Dh                                      ;#0C28: B8 0D 18
        add     al, dh                                         ;#0C2B: 02 C6
        int     21h                                            ;#0C2D: CD 21
        pop     ax                                             ;#0C2F: 58
        ret                                                    ;#0C30: C3
        push    ax                                             ;#0C31: 50
        mov     ax, 180Fh                                      ;#0C32: B8 0F 18
        int     21h                                            ;#0C35: CD 21
        mov     dh, al                                         ;#0C37: 8A F0
        pop     ax                                             ;#0C39: 58
        ret                                                    ;#0C3A: C3
        push    ax                                             ;#0C3B: 50
        push    bx                                             ;#0C3C: 53
        mov     bl, al                                         ;#0C3D: 8A D8
        mov     ax, 4408h                                      ;#0C3F: B8 08 44
        int     21h                                            ;#0C42: CD 21
        cmc                                                    ;#0C44: F5
        jnb     short 0C4Ch                                    ;#0C45: 73 05
        or      al, al                                         ;#0C47: 0A C0
        jnz     short 0C4Ch                                    ;#0C49: 75 01
        stc                                                    ;#0C4B: F9
        pop     bx                                             ;#0C4C: 5B
        pop     ax                                             ;#0C4D: 58
        ret                                                    ;#0C4E: C3
        mov     ax, 3D02h                                      ;#0C4F: B8 02 3D
        int     21h                                            ;#0C52: CD 21
        jb      short 0CA2h                                    ;#0C54: 72 4C
        mov     bx, ax                                         ;#0C56: 8B D8
        mov     ax, 4400h                                      ;#0C58: B8 00 44
        int     21h                                            ;#0C5B: CD 21
        test    dl, 80h                                        ;#0C5D: F6 C2 80
        stc                                                    ;#0C60: F9
        jz      short 0C9Ch                                    ;#0C61: 74 39
        mov     dh, 0                                          ;#0C63: B6 00
        or      dl, 3                                          ;#0C65: 80 CA 03
        mov     ax, 4401h                                      ;#0C68: B8 01 44
        int     21h                                            ;#0C6B: CD 21
        push    cs                                             ;#0C6D: 0E
        pop     ds                                             ;#0C6E: 1F
        xor     cx, cx                                         ;#0C6F: 33 C9
        mov     al, [33Bh]                                     ;#0C71: A0 3B 03
        cmp     al, 0FFh                                       ;#0C74: 3C FF
        jz      short 0C7Fh                                    ;#0C76: 74 07
        xchg    [18h], al                                      ;#0C78: 86 06 18 00
        mov     [33Bh], al                                     ;#0C7C: A2 3B 03
        mov     ah, 46h                                        ;#0C7F: B4 46
        int     21h                                            ;#0C81: CD 21
        inc     cx                                             ;#0C83: 41
        mov     al, [33Ch]                                     ;#0C84: A0 3C 03
        cmp     al, 0FFh                                       ;#0C87: 3C FF
        jz      short 0C92h                                    ;#0C89: 74 07
        xchg    [19h], al                                      ;#0C8B: 86 06 19 00
        mov     [33Ch], al                                     ;#0C8F: A2 3C 03
        mov     ah, 46h                                        ;#0C92: B4 46
        int     21h                                            ;#0C94: CD 21
        inc     cx                                             ;#0C96: 41
        mov     ah, 46h                                        ;#0C97: B4 46
        int     21h                                            ;#0C99: CD 21
        clc                                                    ;#0C9B: F8
        pushf                                                  ;#0C9C: 9C
        mov     ah, 3Eh                                        ;#0C9D: B4 3E
        int     21h                                            ;#0C9F: CD 21
        popf                                                   ;#0CA1: 9D
        ret                                                    ;#0CA2: C3
        mov     byte [0A27h], 0CBh                             ;#0CA3: C6 06 27 0A CB
        mov     byte [0A28h], 0CEh                             ;#0CA8: C6 06 28 0A CE
        xor     al, al                                         ;#0CAD: 32 C0
        cmp     byte [201h], 3Ah                               ;#0CAF: 80 3E 01 02 3A
        jnz     short 0CC5h                                    ;#0CB4: 75 0F
        mov     al, [200h]                                     ;#0CB6: A0 00 02
        and     al, 0DFh                                       ;#0CB9: 24 DF
        mov     [0A27h], al                                    ;#0CBB: A2 27 0A
        db      0C6h                                           ;#0CBE: C6
        push    es                                             ;#0CBF: 06

MSG_0CC0:
        ; "(.:,@"
        ; Format: FORMAT_STRING
        db      "(", 0Ah, ":,@"                                ;#0CC0: 28 0A 3A 2C 40
        ret                                                    ;#0CC5: C3
        mov     word [cs:285h], 0FEAh                          ;#0CC6: 2E C7 06 85 02 EA 0F
        xor     bx, bx                                         ;#0CCD: 33 DB
        mov     si, 33Bh                                       ;#0CCF: BE 3B 03
        call    near 0BEFh                                     ;#0CD2: E8 1A FF
        inc     bx                                             ;#0CD5: 43
        mov     si, 33Ch                                       ;#0CD6: BE 3C 03
        call    near 0BEFh                                     ;#0CD9: E8 13 FF
        mov     bx, 5                                          ;#0CDC: BB 05 00
        mov     cx, 0Fh                                        ;#0CDF: B9 0F 00
        cmp     byte [bx+18h], 0FFh                            ;#0CE2: 80 7F 18 FF
        jz      short 0CECh                                    ;#0CE6: 74 04
        mov     ah, 3Eh                                        ;#0CE8: B4 3E
        int     21h                                            ;#0CEA: CD 21
        inc     bx                                             ;#0CEC: 43
        loop    0CE2h                                          ;#0CED: E2 F3
        test    byte [339h], 2                                 ;#0CEF: F6 06 39 03 02
        jnz     short 0D1Ch                                    ;#0CF4: 75 26
        test    byte [33Ah], 80h                               ;#0CF6: F6 06 3A 03 80
        jz      short 0D1Ch                                    ;#0CFB: 74 1F
        mov     word [PIPE_NAME_PTRS], PIPE_TEMP_NAME_2        ;#0CFD: C7 06 C8 04 DC 04
        mov     word [4CAh], PIPE_TEMP_NAME_1                  ;#0D03: C7 06 CA 04 CC 04
        mov     byte [33Ah], 0                                 ;#0D09: C6 06 3A 03 00
        mov     dx, PIPE_TEMP_NAME_1                           ;#0D0E: BA CC 04
        mov     ah, 41h                                        ;#0D11: B4 41
        int     21h                                            ;#0D13: CD 21
        mov     dx, PIPE_TEMP_NAME_2                           ;#0D15: BA DC 04
        mov     ah, 41h                                        ;#0D18: B4 41
        int     21h                                            ;#0D1A: CD 21
        mov     word [cs:285h], 0FEDh                          ;#0D1C: 2E C7 06 85 02 ED 0F
        mov     al, 0FFh                                       ;#0D23: B0 FF
        xchg    [27Ah], al                                     ;#0D25: 86 06 7A 02
        cmp     al, 0FFh                                       ;#0D29: 3C FF
        jz      short 0D31h                                    ;#0D2B: 74 04
        mov     ah, 2Eh                                        ;#0D2D: B4 2E
        int     21h                                            ;#0D2F: CD 21
        ret                                                    ;#0D31: C3
        push    ax                                             ;#0D32: 50
        push    bx                                             ;#0D33: 53
        call    near 0C00h                                     ;#0D34: E8 C9 FE
        mov     ah, 51h                                        ;#0D37: B4 51
        int     21h                                            ;#0D39: CD 21
        mov     ds, bx                                         ;#0D3B: 8E DB
        lds     bx, [34h]                                      ;#0D3D: C5 1E 34 00
        mov     [cs:27Dh], bx                                  ;#0D41: 2E 89 1E 7D 02
        mov     [cs:27Fh], ds                                  ;#0D46: 2E 8C 1E 7F 02

MSG_0D4B:
        ; "...ú{"
        ; Format: FORMAT_STRING
        db      8Bh, 7, ".ú{"                                  ;#0D4B: 8B 07 2E A3 7B
        add     ch, [1AA0h]                                    ;#0D50: 02 2E A0 1A
        add     [bp+si+89E0h], cl                              ;#0D54: 00 8A E0 89
        pop     es                                             ;#0D58: 07
        jmp     short 0D6Bh                                    ;#0D59: EB 10

MSG_PS:
        ; "PS.í{"
        ; Format: FORMAT_STRING
        db      "PS.í{"                                        ;#0D5B: 50 53 2E A1 7B
        add     ch, [1EC5h]                                    ;#0D60: 02 2E C5 1E
        jnl     short 0D68h                                    ;#0D64: 7D 02
        mov     [bx], ax                                       ;#0D66: 89 07
        call    near 0C00h                                     ;#0D68: E8 95 FE
        pop     bx                                             ;#0D6B: 5B
        pop     ax                                             ;#0D6C: 58
        push    cs                                             ;#0D6D: 0E
        pop     ds                                             ;#0D6E: 1F
        ret                                                    ;#0D6F: C3
        cmp     word [272h], 0                                 ;#0D70: 83 3E 72 02 00
        jz      short 0D7Bh                                    ;#0D75: 74 04
        clc                                                    ;#0D77: F8
        ret                                                    ;#0D78: C3
        stc                                                    ;#0D79: F9
        ret                                                    ;#0D7A: C3
        mov     dx, 4F70h                                      ;#0D7B: BA 70 4F
        mov     cl, 4                                          ;#0D7E: B1 04
        shr     dx, cl                                         ;#0D80: D3 EA
        mov     cx, dx                                         ;#0D82: 8B CA
        mov     bx, 0FFFFh                                     ;#0D84: BB FF FF
        mov     ah, 48h                                        ;#0D87: B4 48
        int     21h                                            ;#0D89: CD 21
        cmp     bx, cx                                         ;#0D8B: 3B D9
        mov     dx, 9B0h                                       ;#0D8D: BA B0 09
        jbe     short 0D79h                                    ;#0D90: 76 E7
        mov     ah, 48h                                        ;#0D92: B4 48
        int     21h                                            ;#0D94: CD 21
        mov     dx, 9BFh                                       ;#0D96: BA BF 09
        jb      short 0D79h                                    ;#0D99: 72 DE
        mov     [272h], ax                                     ;#0D9B: A3 72 02
        sub     bx, cx                                         ;#0D9E: 2B D9
        mov     [274h], bx                                     ;#0DA0: 89 1E 74 02
        add     ax, bx                                         ;#0DA4: 03 C3
        mov     [252h], ax                                     ;#0DA6: A3 52 02
        add     ax, cx                                         ;#0DA9: 03 C1
        mov     [2], ax                                        ;#0DAB: A3 02 00
        clc                                                    ;#0DAE: F8
        ret                                                    ;#0DAF: C3
        push    ds                                             ;#0DB0: 1E
        push    ds                                             ;#0DB1: 1E
        pop     es                                             ;#0DB2: 07
        mov     di, 337h                                       ;#0DB3: BF 37 03
        mov     ds, [337h]                                     ;#0DB6: 8E 1E 37 03
        xor     si, si                                         ;#0DBA: 33 F6
        mov     cx, 629h                                       ;#0DBC: B9 29 06
        sub     cx, di                                         ;#0DBF: 2B CF
        rep     movsb                                          ;#0DC1: F3 A4
        push    ds                                             ;#0DC3: 1E
        pop     es                                             ;#0DC4: 07
        pop     ds                                             ;#0DC5: 1F
        mov     ah, 49h                                        ;#0DC6: B4 49
        int     21h                                            ;#0DC8: CD 21
        mov     al, [336h]                                     ;#0DCA: A0 36 03
        not     al                                             ;#0DCD: F6 D0
        and     [339h], al                                     ;#0DCF: 20 06 39 03
        xor     ax, ax                                         ;#0DD3: 33 C0
        cmp     [337h], ax                                     ;#0DD5: 39 06 37 03
        jnz     short 0DDEh                                    ;#0DD9: 75 03
        mov     [336h], al                                     ;#0DDB: A2 36 03
        ret                                                    ;#0DDE: C3
        push    ds                                             ;#0DDF: 1E
        pop     es                                             ;#0DE0: 07
        mov     ax, [2Ch]                                      ;#0DE1: A1 2C 00
        or      ax, ax                                         ;#0DE4: 0B C0
        jz      short 0E2Ch                                    ;#0DE6: 74 44
        mov     ds, ax                                         ;#0DE8: 8E D8
        xor     si, si                                         ;#0DEA: 33 F6
        mov     di, MSG_COMSPEC_COMMAND_PRV                    ;#0DEC: BF 40 0B
        cmp     byte [si], 0                                   ;#0DEF: 80 3C 00
        jz      short 0E2Ch                                    ;#0DF2: 74 38
        lodsb                                                  ;#0DF4: AC
        inc     di                                             ;#0DF5: 47
        cmp     [es:di-1], al                                  ;#0DF6: 26 38 45 FF
        jz      short 0E03h                                    ;#0DFA: 74 07
        or      al, al                                         ;#0DFC: 0A C0
        jz      short 0DECh                                    ;#0DFE: 74 EC
        lodsb                                                  ;#0E00: AC
        jmp     short 0DFCh                                    ;#0E01: EB F9
        cmp     al, 3Dh                                        ;#0E03: 3C 3D
        jnz     short 0DF4h                                    ;#0E05: 75 ED
        mov     al, [si]                                       ;#0E07: 8A 04
        cmp     al, 20h                                        ;#0E09: 3C 20
        jbe     short 0E2Ch                                    ;#0E0B: 76 1F
        cmp     al, 3Bh                                        ;#0E0D: 3C 3B
        jz      short 0E2Ch                                    ;#0E0F: 74 1B
        cmp     al, 2Ch                                        ;#0E11: 3C 2C
        jz      short 0E2Ch                                    ;#0E13: 74 17
        push    es                                             ;#0E15: 06
        push    ds                                             ;#0E16: 1E
        pop     es                                             ;#0E17: 07
        mov     di, si                                         ;#0E18: 8B FE
        push    cx                                             ;#0E1A: 51
        mov     cx, 50h                                        ;#0E1B: B9 50 00
        xor     al, al                                         ;#0E1E: 32 C0
        repne   scasb                                          ;#0E20: F2 AE
        pop     cx                                             ;#0E22: 59
        pop     es                                             ;#0E23: 07
        jnz     short 0E2Ch                                    ;#0E24: 75 06
        mov     cx, di                                         ;#0E26: 8B CF
        sub     cx, si                                         ;#0E28: 2B CE
        clc                                                    ;#0E2A: F8
        ret                                                    ;#0E2B: C3
        stc                                                    ;#0E2C: F9
        ret                                                    ;#0E2D: C3
        push    ds                                             ;#0E2E: 1E
        push    es                                             ;#0E2F: 06
        push    si                                             ;#0E30: 56
        push    di                                             ;#0E31: 57
        call    near 0DDFh                                     ;#0E32: E8 AA FF
        jb      short 0E3Ch                                    ;#0E35: 72 05
        mov     di, 200h                                       ;#0E37: BF 00 02
        rep     movsb                                          ;#0E3A: F3 A4
        pop     di                                             ;#0E3C: 5F
        pop     si                                             ;#0E3D: 5E
        pop     es                                             ;#0E3E: 07
        pop     ds                                             ;#0E3F: 1F
        ret                                                    ;#0E40: C3
        mov     dx, 81Bh                                       ;#0E41: BA 1B 08
        push    dx                                             ;#0E44: 52
        call    near 0C31h                                     ;#0E45: E8 E9 FD
        mov     [28Eh], dx                                     ;#0E48: 89 16 8E 02
        cmp     dh, 1                                          ;#0E4C: 80 FE 01
        jz      short 0E54h                                    ;#0E4F: 74 03
        call    near 0C1Eh                                     ;#0E51: E8 CA FD
        pop     dx                                             ;#0E54: 5A
        call    near 0D32h                                     ;#0E55: E8 DA FE
        call    near 0E6Dh                                     ;#0E58: E8 12 00
        call    near MSG_PS                                    ;#0E5B: E8 FD FE
        push    dx                                             ;#0E5E: 52
        mov     dx, [28Eh]                                     ;#0E5F: 8B 16 8E 02
        cmp     dh, 1                                          ;#0E63: 80 FE 01
        jz      short 0E6Bh                                    ;#0E66: 74 03
        call    near 0C21h                                     ;#0E68: E8 B6 FD
        pop     dx                                             ;#0E6B: 5A
        ret                                                    ;#0E6C: C3
        push    ax                                             ;#0E6D: 50
        push    dx                                             ;#0E6E: 52
        push    si                                             ;#0E6F: 56
        mov     si, dx                                         ;#0E70: 8B F2
        lodsb                                                  ;#0E72: AC
        cmp     al, 0B0h                                       ;#0E73: 3C B0
        jb      short 0E8Dh                                    ;#0E75: 72 16
        cmp     al, 0FFh                                       ;#0E77: 3C FF
        jz      short 0E95h                                    ;#0E79: 74 1A
        sub     al, 0B0h                                       ;#0E7B: 2C B0
        cbw                                                    ;#0E7D: 98
        shl     ax, 1                                          ;#0E7E: D1 E0
        push    bx                                             ;#0E80: 53
        mov     bx, ax                                         ;#0E81: 8B D8
        mov     dx, [bx+900h]                                  ;#0E83: 8B 97 00 09
        pop     bx                                             ;#0E87: 5B
        call    near 0E6Dh                                     ;#0E88: E8 E2 FF
        jmp     short 0E72h                                    ;#0E8B: EB E5
        mov     dl, al                                         ;#0E8D: 8A D0
        mov     ah, 2                                          ;#0E8F: B4 02
        int     21h                                            ;#0E91: CD 21
        jmp     short 0E72h                                    ;#0E93: EB DD
        pop     si                                             ;#0E95: 5E
        pop     dx                                             ;#0E96: 5A
        pop     ax                                             ;#0E97: 58
        ret                                                    ;#0E98: C3
        cli                                                    ;#0E99: FA
        push    cs                                             ;#0E9A: 0E
        pop     ss                                             ;#0E9B: 17
        mov     sp, 200h                                       ;#0E9C: BC 00 02
        sti                                                    ;#0E9F: FB
        cld                                                    ;#0EA0: FC
        push    cs                                             ;#0EA1: 0E
        pop     ds                                             ;#0EA2: 1F
        push    cs                                             ;#0EA3: 0E
        pop     es                                             ;#0EA4: 07
        mov     si, 264h                                       ;#0EA5: BE 64 02
        mov     di, 0Ah                                        ;#0EA8: BF 0A 00
        mov     cx, 7                                          ;#0EAB: B9 07 00
        rep     movsw                                          ;#0EAE: F3 A5
        xor     al, al                                         ;#0EB0: 32 C0
        mov     [287h], al                                     ;#0EB2: A2 87 02
        mov     [288h], al                                     ;#0EB5: A2 88 02
        mov     [335h], al                                     ;#0EB8: A2 35 03
        cmp     [290h], al                                     ;#0EBB: 38 06 90 02
        jnz     short 0ED2h                                    ;#0EBF: 75 11
        cmp     [278h], al                                     ;#0EC1: 38 06 78 02
        jz      short 0ECAh                                    ;#0EC5: 74 03
        call    near 0B62h                                     ;#0EC7: E8 98 FC
        call    near 0C1Eh                                     ;#0ECA: E8 51 FD
        call    near 0D70h                                     ;#0ECD: E8 A0 FE
        jb      short 0EF8h                                    ;#0ED0: 72 26
        mov     al, [339h]                                     ;#0ED2: A0 39 03
        test    al, 7                                          ;#0ED5: A8 07
        jnz     short 0EDDh                                    ;#0ED7: 75 04
        test    al, 0D0h                                       ;#0ED9: A8 D0
        jnz     short 0EFBh                                    ;#0EDB: 75 1E
        mov     byte [336h], 0                                 ;#0EDD: C6 06 36 03 00
        call    near 0CC6h                                     ;#0EE2: E8 E1 FD
        cmp     byte [278h], 0                                 ;#0EE5: 80 3E 78 02 00
        jz      short 0EF4h                                    ;#0EEA: 74 08
        call    near 116Ah                                     ;#0EEC: E8 7B 02
        mov     byte [278h], 0                                 ;#0EEF: C6 06 78 02 00
        jmp     far word [250h]                                ;#0EF4: FF 2E 50 02
        jmp     near 11F4h                                     ;#0EF8: E9 F9 02
        call    near 0CC6h                                     ;#0EFB: E8 C8 FD
        xor     ax, ax                                         ;#0EFE: 33 C0
        xchg    [272h], ax                                     ;#0F00: 87 06 72 02
        mov     es, ax                                         ;#0F04: 8E C0
        mov     ah, 49h                                        ;#0F06: B4 49
        int     21h                                            ;#0F08: CD 21
        mov     al, [339h]                                     ;#0F0A: A0 39 03
        test    al, 10h                                        ;#0F0D: A8 10
        jnz     short 0F28h                                    ;#0F0F: 75 17
        test    al, 40h                                        ;#0F11: A8 40
        jnz     short 0F2Eh                                    ;#0F13: 75 19
        test    al, 80h                                        ;#0F15: A8 80
        jnz     short 0F59h                                    ;#0F17: 75 40
        test    byte [339h], 50h                               ;#0F19: F6 06 39 03 50
        jnz     short 0F25h                                    ;#0F1E: 75 05
        or      byte [339h], 80h                               ;#0F20: 80 0E 39 03 80
        jmp     near 0E99h                                     ;#0F25: E9 71 FF
        call    near 0DB0h                                     ;#0F28: E8 85 FE
        jmp     near 0E99h                                     ;#0F2B: E9 6B FF
        mov     byte [336h], 0                                 ;#0F2E: C6 06 36 03 00
        call    near 0DB0h                                     ;#0F33: E8 7A FE
        xor     ax, ax                                         ;#0F36: 33 C0
        mov     [289h], ax                                     ;#0F38: A3 89 02
        mov     bx, [623h]                                     ;#0F3B: 8B 1E 23 06
        mov     ah, 50h                                        ;#0F3F: B4 50
        int     21h                                            ;#0F41: CD 21
        mov     dx, [621h]                                     ;#0F43: 8B 16 21 06
        call    near 0C21h                                     ;#0F47: E8 D7 FC
        xor     ax, ax                                         ;#0F4A: 33 C0
        xchg    [290h], al                                     ;#0F4C: 86 06 90 02
        mov     byte [278h], 1                                 ;#0F50: C6 06 78 02 01
        jmp     far word [625h]                                ;#0F55: FF 2E 25 06
        cmp     byte [277h], 0                                 ;#0F59: 80 3E 77 02 00
        jz      short 0F68h                                    ;#0F5E: 74 08
        and     byte [339h], 7Fh                               ;#0F60: 80 26 39 03 7F
        jmp     near 0E99h                                     ;#0F65: E9 31 FF
        mov     dx, [28Ch]                                     ;#0F68: 8B 16 8C 02
        call    near 0C21h                                     ;#0F6C: E8 B2 FC
        push    cs                                             ;#0F6F: 0E
        pop     es                                             ;#0F70: 07
        mov     si, 256h                                       ;#0F71: BE 56 02
        mov     di, 0Ah                                        ;#0F74: BF 0A 00
        mov     cx, 7                                          ;#0F77: B9 07 00
        rep     movsw                                          ;#0F7A: F3 A5
        mov     ax, 4C00h                                      ;#0F7C: B8 00 4C
        int     21h                                            ;#0F7F: CD 21
        sti                                                    ;#0F81: FB
        cld                                                    ;#0F82: FC
        mov     ah, 0Dh                                        ;#0F83: B4 0D
        int     21h                                            ;#0F85: CD 21
        push    cs                                             ;#0F87: 0E
        pop     ds                                             ;#0F88: 1F
        and     byte [339h], 0FCh                              ;#0F89: 80 26 39 03 FC
        or      byte [336h], 3                                 ;#0F8E: 80 0E 36 03 03
        call    near 0F99h                                     ;#0F93: E8 03 00
        stc                                                    ;#0F96: F9
        retf                                                   ;#0F97: CB
        iret                                                   ;#0F98: CF
        call    near 0FBEh                                     ;#0F99: E8 22 00
        jz      short 0FBDh                                    ;#0F9C: 74 1F
        call    near 0E41h                                     ;#0F9E: E8 A0 FE
        mov     dx, 970h                                       ;#0FA1: BA 70 09
        call    near 0BB7h                                     ;#0FA4: E8 10 FC
        cmp     al, 4Eh                                        ;#0FA7: 3C 4E
        jz      short 0FBDh                                    ;#0FA9: 74 12
        cmp     al, 53h                                        ;#0FAB: 3C 53
        jz      short 0FB3h                                    ;#0FAD: 74 04
        cmp     al, 0Dh                                        ;#0FAF: 3C 0D
        jnz     short 0FA1h                                    ;#0FB1: 75 EE
        and     byte [339h], 0FBh                              ;#0FB3: 80 26 39 03 FB
        or      byte [336h], 4                                 ;#0FB8: 80 0E 36 03 04
        ret                                                    ;#0FBD: C3
        push    ds                                             ;#0FBE: 1E
        push    bx                                             ;#0FBF: 53
        xor     bx, bx                                         ;#0FC0: 33 DB
        test    byte [bx+339h], 4                              ;#0FC2: F6 87 39 03 04
        jnz     short 0FE2h                                    ;#0FC7: 75 19
        test    byte [bx+339h], 10h                            ;#0FC9: F6 87 39 03 10
        jz      short 0FE2h                                    ;#0FCE: 74 12
        cmp     word [bx+337h], 0                              ;#0FD0: 83 BF 37 03 00
        jz      short 0FE2h                                    ;#0FD5: 74 0B
        mov     ds, [bx+337h]                                  ;#0FD7: 8E 9F 37 03
        mov     bx, 337h                                       ;#0FDB: BB 37 03
        neg     bx                                             ;#0FDE: F7 DB
        jmp     short 0FC2h                                    ;#0FE0: EB E0
        pop     bx                                             ;#0FE2: 5B
        pop     ds                                             ;#0FE3: 1F
        ret                                                    ;#0FE4: C3
        jmp     word [cs:285h]                                 ;#0FE5: 2E FF 26 85 02
        mov     al, 0                                          ;#0FEA: B0 00
        iret                                                   ;#0FEC: CF
        sti                                                    ;#0FED: FB
        cld                                                    ;#0FEE: FC
        push    ds                                             ;#0FEF: 1E
        push    es                                             ;#0FF0: 06

MSG_UVWRQSPI:
        ; "UVWRQSP."
        ; Format: FORMAT_STRING
        db      "UVWRQSP", 8Bh                                 ;#0FF1: 55 56 57 52 51 53 50 8B
        in      al, dx                                         ;#0FF9: EC
        push    cs                                             ;#0FFA: 0E
        pop     ds                                             ;#0FFB: 1F
        push    cs                                             ;#0FFC: 0E
        pop     es                                             ;#0FFD: 07
        mov     byte [993h], 0CEh                              ;#0FFE: C6 06 93 09 CE
        mov     byte [994h], 0CEh                              ;#1003: C6 06 94 09 CE
        mov     byte [987h], 0FFh                              ;#1008: C6 06 87 09 FF
        call    near 107Ch                                     ;#100D: E8 6C 00
        cmp     byte [987h], 0FFh                              ;#1010: 80 3E 87 09 FF
        jnz     short 101Ah                                    ;#1015: 75 03
        call    near 10FDh                                     ;#1017: E8 E3 00
        mov     dx, 985h                                       ;#101A: BA 85 09
        call    near 0E44h                                     ;#101D: E8 24 FE
        or      bh, bh                                         ;#1020: 0A FF
        jz      short 1029h                                    ;#1022: 74 05
        call    near 11E3h                                     ;#1024: E8 BC 01
        jmp     short 1060h                                    ;#1027: EB 37
        mov     dx, 9A3h                                       ;#1029: BA A3 09
        call    near 0BB7h                                     ;#102C: E8 88 FB
        cmp     al, 3                                          ;#102F: 3C 03

MSG_1031:
        ; "t-<.u"
        ; Format: FORMAT_STRING
        db      "t-<", 0Dh, "u"                                ;#1031: 74 2D 3C 0D 75
        add     dh, [bx+si+0BF50h]                             ;#1036: 02 B0 50 BF
        lodsb                                                  ;#103A: AC
        or      [bx+di+4], di                                  ;#103B: 09 B9 04 00
        repne   scasb                                          ;#103F: F2 AE
        jnz     short 1029h                                    ;#1041: 75 E6
        dec     cl                                             ;#1043: FE C9
        and     cl, 3                                          ;#1045: 80 E1 03
        cmp     cl, 2                                          ;#1048: 80 F9 02

MSG_104B:
        ; "u"Ç>."
        ; Format: FORMAT_STRING
        db      "u", 22h, "Ç>", 88h                            ;#104B: 75 22 80 3E 88
        add     al, [bx+si]                                    ;#1050: 02 00
        jnz     short 1060h                                    ;#1052: 75 0C
        and     byte [339h], 0FCh                              ;#1054: 80 26 39 03 FC
        or      byte [336h], 3                                 ;#1059: 80 0E 36 03 03
        jmp     short 106Fh                                    ;#105E: EB 0F
        and     byte [339h], 0FCh                              ;#1060: 80 26 39 03 FC
        or      byte [336h], 3                                 ;#1065: 80 0E 36 03 03
        call    near 0F99h                                     ;#106A: E8 2C FF
        mov     cl, 2                                          ;#106D: B1 02
        mov     [bp], cl                                       ;#106F: 88 4E 00

MSG_YZ:
        ; "X[YZ_^]."
        ; Format: FORMAT_STRING
        db      "X[YZ_^]", 7                                   ;#1072: 58 5B 59 5A 5F 5E 5D 07
        pop     ds                                             ;#107A: 1F
        iret                                                   ;#107B: CF
        add     al, 41h                                        ;#107C: 04 41
        mov     [856h], al                                     ;#107E: A2 56 08
        push    ds                                             ;#1081: 1E
        lds     si, [bp+0Ah]                                   ;#1082: C5 76 0A
        mov     bl, [si+5]                                     ;#1085: 8A 5C 05
        add     si, 0Ah                                        ;#1088: 83 C6 0A
        mov     di, 869h                                       ;#108B: BF 69 08
        movsw                                                  ;#108E: A5
        movsw                                                  ;#108F: A5
        movsw                                                  ;#1090: A5
        movsw                                                  ;#1091: A5
        pop     ds                                             ;#1092: 1F
        test    ah, 1                                          ;#1093: F6 C4 01
        mov     cl, 0D9h                                       ;#1096: B1 D9
        jz      short 109Ch                                    ;#1098: 74 02
        mov     cl, 0DAh                                       ;#109A: B1 DA
        test    bl, 80h                                        ;#109C: F6 C3 80
        mov     ch, 0DCh                                       ;#109F: B5 DC
        mov     bh, 0                                          ;#10A1: B7 00
        jnz     short 10B5h                                    ;#10A3: 75 10
        mov     ch, 0DBh                                       ;#10A5: B5 DB
        mov     bh, [287h]                                     ;#10A7: 8A 3E 87 02
        test    ah, 80h                                        ;#10AB: F6 C4 80
        jz      short 10B5h                                    ;#10AE: 74 05
        mov     byte [987h], 0DFh                              ;#10B0: C6 06 87 09 DF
        db      88h                                            ;#10B5: 88
        push    cs                                             ;#10B6: 0E

MSG_10B7:
        ; "É....."
        ; Format: FORMAT_STRING
        db      "É", 9, 88h, ".", 91h, 9                       ;#10B7: 90 09 88 2E 91 09
        test    ah, 80h                                        ;#10BD: F6 C4 80
        jnz     short 10D2h                                    ;#10C0: 75 10
        mov     al, ah                                         ;#10C2: 8A C4
        shr     al, 1                                          ;#10C4: D0 E8
        and     al, 3                                          ;#10C6: 24 03
        add     al, 0E1h                                       ;#10C8: 04 E1
        mov     [898h], al                                     ;#10CA: A2 98 08
        mov     byte [993h], 0E0h                              ;#10CD: C6 06 93 09 E0
        mov     si, 996h                                       ;#10D2: BE 96 09
        mov     di, 9A3h                                       ;#10D5: BF A3 09
        mov     cx, di                                         ;#10D8: 8B CF
        sub     cx, si                                         ;#10DA: 2B CE
        rep     movsb                                          ;#10DC: F3 A4
        inc     si                                             ;#10DE: 46
        inc     si                                             ;#10DF: 46
        mov     di, 9ADh                                       ;#10E0: BF AD 09
        test    ah, 10h                                        ;#10E3: F6 C4 10
        call    near 10F2h                                     ;#10E6: E8 09 00
        test    ah, 20h                                        ;#10E9: F6 C4 20
        call    near 10F2h                                     ;#10EC: E8 03 00
        test    ah, 8                                          ;#10EF: F6 C4 08
        jnz     short 10FAh                                    ;#10F2: 75 06
        mov     byte [si], 0CEh                                ;#10F4: C6 04 CE
        mov     byte [di], 43h                                 ;#10F7: C6 05 43
        inc     si                                             ;#10FA: 46
        inc     di                                             ;#10FB: 47
        ret                                                    ;#10FC: C3
        push    bx                                             ;#10FD: 53
        push    bp                                             ;#10FE: 55
        push    ds                                             ;#10FF: 1E
        push    es                                             ;#1100: 06
        mov     ah, 59h                                        ;#1101: B4 59
        int     21h                                            ;#1103: CD 21
        push    es                                             ;#1105: 06
        pop     ds                                             ;#1106: 1F
        mov     si, di                                         ;#1107: 8B F7
        pop     es                                             ;#1109: 07
        mov     di, 8DEh                                       ;#110A: BF DE 08
        mov     cx, 0Bh                                        ;#110D: B9 0B 00
        pop     ds                                             ;#1110: 1F
        pop     bp                                             ;#1111: 5D
        pop     bx                                             ;#1112: 5B
        mov     cl, 0Ch                                        ;#1113: B1 0C
        sub     al, 13h                                        ;#1115: 2C 13
        jb      short 112Ah                                    ;#1117: 72 11
        mov     cl, 12h                                        ;#1119: B1 12
        cmp     al, cl                                         ;#111B: 3A C1
        jnb     short 112Ah                                    ;#111D: 73 0B
        mov     cl, al                                         ;#111F: 8A C8
        cmp     al, 0Fh                                        ;#1121: 3C 0F
        jnz     short 112Ah                                    ;#1123: 75 05
        mov     byte [994h], 0E5h                              ;#1125: C6 06 94 09 E5
        add     cl, 0B0h                                       ;#112A: 80 C1 B0
        mov     [987h], cl                                     ;#112D: 88 0E 87 09
        ret                                                    ;#1131: C3
        cli                                                    ;#1132: FA
        push    cs                                             ;#1133: 0E
        pop     ss                                             ;#1134: 17
        mov     sp, 200h                                       ;#1135: BC 00 02
        sti                                                    ;#1138: FB
        mov     ax, 4B00h                                      ;#1139: B8 00 4B
        int     21h                                            ;#113C: CD 21
        cld                                                    ;#113E: FC
        jnb     short 1158h                                    ;#113F: 73 17
        push    cs                                             ;#1141: 0E
        pop     ds                                             ;#1142: 1F
        mov     bx, 0Ch                                        ;#1143: BB 0C 00
        cmp     ax, bx                                         ;#1146: 3B C3
        jnb     short 114Ch                                    ;#1148: 73 02
        mov     bx, ax                                         ;#114A: 8B D8
        shl     bx, 1                                          ;#114C: D1 E3
        mov     dx, [bx+0B0Ch]                                 ;#114E: 8B 97 0C 0B
        call    near 0E44h                                     ;#1152: E8 EF FC
        jmp     near 0E99h                                     ;#1155: E9 41 FD
        mov     ah, 4Dh                                        ;#1158: B4 4D
        int     21h                                            ;#115A: CD 21
        mov     [cs:28Bh], al                                  ;#115C: 2E A2 8B 02
        jmp     short 1155h                                    ;#1160: EB F3
        call    near 0C3Bh                                     ;#1162: E8 D6 FA
        retf                                                   ;#1165: CB
        call    near 0C4Fh                                     ;#1166: E8 E6 FA
        retf                                                   ;#1169: CB
        call    near 0B93h                                     ;#116A: E8 26 FA
        jz      short 1172h                                    ;#116D: 74 03
        call    near 1183h                                     ;#116F: E8 11 00
        mov     es, [252h]                                     ;#1172: 8E 06 52 02
        mov     [es:4660h], cs                                 ;#1176: 26 8C 0E 60 46
        call    near 0B81h                                     ;#117B: E8 03 FA
        mov     [es:4662h], ax                                 ;#117E: 26 A3 62 46
        ret                                                    ;#1182: C3
        call    near 0E2Eh                                     ;#1183: E8 A8 FC
        mov     byte [287h], 1                                 ;#1186: C6 06 87 02 01
        mov     dx, 200h                                       ;#118B: BA 00 02
        mov     ax, 3D00h                                      ;#118E: B8 00 3D
        int     21h                                            ;#1191: CD 21
        jb      short 11CFh                                    ;#1193: 72 3A
        xor     cx, cx                                         ;#1195: 33 C9
        mov     dx, 2020h                                      ;#1197: BA 20 20
        mov     bx, ax                                         ;#119A: 8B D8
        mov     ax, 4200h                                      ;#119C: B8 00 42
        int     21h                                            ;#119F: CD 21
        jb      short 11BCh                                    ;#11A1: 72 19
        mov     cx, 4E70h                                      ;#11A3: B9 70 4E
        inc     cx                                             ;#11A6: 41
        mov     ds, [252h]                                     ;#11A7: 8E 1E 52 02
        mov     dx, COMMAND_ENTRY                              ;#11AB: BA 00 01
        mov     ah, 3Fh                                        ;#11AE: B4 3F
        int     21h                                            ;#11B0: CD 21
        push    cs                                             ;#11B2: 0E
        pop     ds                                             ;#11B3: 1F
        jb      short 11BCh                                    ;#11B4: 72 06
        dec     cx                                             ;#11B6: 49
        cmp     ax, cx                                         ;#11B7: 3B C1
        jz      short 11BCh                                    ;#11B9: 74 01
        stc                                                    ;#11BB: F9
        pushf                                                  ;#11BC: 9C
        mov     ah, 3Eh                                        ;#11BD: B4 3E
        int     21h                                            ;#11BF: CD 21
        popf                                                   ;#11C1: 9D
        jb      short 11D8h                                    ;#11C2: 72 14
        call    near 0B93h                                     ;#11C4: E8 CC F9
        jnz     short 11D8h                                    ;#11C7: 75 0F
        mov     byte [287h], 0                                 ;#11C9: C6 06 87 02 00
        ret                                                    ;#11CE: C3
        cmp     al, 4                                          ;#11CF: 3C 04
        jnz     short 11DEh                                    ;#11D1: 75 0B
        mov     dx, 9D5h                                       ;#11D3: BA D5 09
        jmp     short 11F4h                                    ;#11D6: EB 1C
        mov     dx, 9FEh                                       ;#11D8: BA FE 09
        call    near 0E44h                                     ;#11DB: E8 66 FC
        call    near 11E3h                                     ;#11DE: E8 02 00
        jmp     short 1183h                                    ;#11E1: EB A0
        call    near 0CA3h                                     ;#11E3: E8 BD FA
        call    near 0C3Bh                                     ;#11E6: E8 52 FA
        mov     dx, 9DBh                                       ;#11E9: BA DB 09
        jnb     short 11F4h                                    ;#11EC: 73 06
        mov     dx, 0A16h                                      ;#11EE: BA 16 0A
        jmp     near 0BB7h                                     ;#11F1: E9 C3 F9
        call    near 0E44h                                     ;#11F4: E8 4D FC
        mov     al, [339h]                                     ;#11F7: A0 39 03
        and     al, 0F8h                                       ;#11FA: 24 F8
        mov     ah, 0                                          ;#11FC: B4 00
        xor     dx, dx                                         ;#11FE: 33 D2
        xchg    [289h], dx                                     ;#1200: 87 16 89 02
        or      dx, dx                                         ;#1204: 0B D2
        jz      short 1214h                                    ;#1206: 74 0C
        mov     ah, 80h                                        ;#1208: B4 80
        cmp     dx, 80h                                        ;#120A: 81 FA 80 00
        jnz     short 122Ah                                    ;#120E: 75 1A
        mov     ah, 40h                                        ;#1210: B4 40
        jmp     short 122Ah                                    ;#1212: EB 16
        test    al, 0D0h                                       ;#1214: A8 D0
        jnz     short 122Ah                                    ;#1216: 75 12
        mov     ah, 80h                                        ;#1218: B4 80
        cmp     byte [277h], 0                                 ;#121A: 80 3E 77 02 00
        jz      short 122Ah                                    ;#121F: 74 09
        mov     dx, 0A4Ch                                      ;#1221: BA 4C 0A
        call    near 0E44h                                     ;#1224: E8 1D FC
        sti                                                    ;#1227: FB
        jmp     short 1228h                                    ;#1228: EB FE
        or      al, ah                                         ;#122A: 0A C4
        mov     [339h], al                                     ;#122C: A2 39 03
        or      byte [336h], 7                                 ;#122F: 80 0E 36 03 07
        mov     dx, 0A6Ah                                      ;#1234: BA 6A 0A
        call    near 0E44h                                     ;#1237: E8 0A FC
        mov     byte [290h], 0FFh                              ;#123A: C6 06 90 02 FF
        jmp     near 0E99h                                     ;#123F: E9 57 FC
        cld                                                    ;#1242: FC
        push    cs                                             ;#1243: 0E
        pop     es                                             ;#1244: 07
        lodsb                                                  ;#1245: AC
        and     al, 7Fh                                        ;#1246: 24 7F
        cbw                                                    ;#1248: 98
        mov     cx, ax                                         ;#1249: 8B C8
        mov     di, 80h                                        ;#124B: BF 80 00
        rep     movsb                                          ;#124E: F3 A4
        mov     al, 0Dh                                        ;#1250: B0 0D
        stosb                                                  ;#1252: AA
        push    cs                                             ;#1253: 0E
        pop     ds                                             ;#1254: 1F
        pop     word [625h]                                    ;#1255: 8F 06 25 06
        pop     word [627h]                                    ;#1259: 8F 06 27 06
        mov     ah, 51h                                        ;#125D: B4 51
        int     21h                                            ;#125F: CD 21
        mov     [623h], bx                                     ;#1261: 89 1E 23 06
        mov     bx, cs                                         ;#1265: 8C CB
        mov     ah, 50h                                        ;#1267: B4 50
        int     21h                                            ;#1269: CD 21
        call    near 0C31h                                     ;#126B: E8 C3 F9
        mov     [621h], dx                                     ;#126E: 89 16 21 06
        call    near 1294h                                     ;#1272: E8 1F 00
        mov     dx, 0A81h                                      ;#1275: BA 81 0A
        jb      short 127Dh                                    ;#1278: 72 03
        jmp     near 0E99h                                     ;#127A: E9 1C FC
        call    near 0E44h                                     ;#127D: E8 C4 FB
        mov     bx, [623h]                                     ;#1280: 8B 1E 23 06
        mov     ah, 50h                                        ;#1284: B4 50
        int     21h                                            ;#1286: CD 21
        mov     ax, 0FFh                                       ;#1288: B8 FF 00
        push    word [627h]                                    ;#128B: FF 36 27 06
        push    word [625h]                                    ;#128F: FF 36 25 06
        iret                                                   ;#1293: CF
        mov     bx, 629h                                       ;#1294: BB 29 06
        sub     bx, 337h                                       ;#1297: 81 EB 37 03
        add     bx, 0Fh                                        ;#129B: 83 C3 0F
        mov     cl, 4                                          ;#129E: B1 04
        shr     bx, cl                                         ;#12A0: D3 EB
        mov     ah, 48h                                        ;#12A2: B4 48
        int     21h                                            ;#12A4: CD 21
        jb      short 12E2h                                    ;#12A6: 72 3A
        mov     es, ax                                         ;#12A8: 8E C0
        xor     di, di                                         ;#12AA: 33 FF
        mov     si, 337h                                       ;#12AC: BE 37 03
        mov     cx, 629h                                       ;#12AF: B9 29 06
        sub     cx, si                                         ;#12B2: 2B CE
        rep     movsb                                          ;#12B4: F3 A4
        mov     [337h], es                                     ;#12B6: 8C 06 37 03
        xor     al, al                                         ;#12BA: 32 C0
        mov     [33Dh], al                                     ;#12BC: A2 3D 03
        mov     [33Eh], al                                     ;#12BF: A2 3E 03
        mov     [38Eh], al                                     ;#12C2: A2 8E 03
        mov     [33Ah], al                                     ;#12C5: A2 3A 03
        mov     [339h], al                                     ;#12C8: A2 39 03
        mov     [336h], al                                     ;#12CB: A2 36 03
        mov     al, 0FFh                                       ;#12CE: B0 FF
        mov     [33Bh], al                                     ;#12D0: A2 3B 03
        mov     [33Ch], al                                     ;#12D3: A2 3C 03
        mov     word [289h], 80h                               ;#12D6: C7 06 89 02 80 00
        mov     byte [278h], 1                                 ;#12DC: C6 06 78 02 01
        clc                                                    ;#12E1: F8
        ret                                                    ;#12E2: C3
        push    es                                             ;#12E3: 06
        push    bx                                             ;#12E4: 53
        mov     es, [2Ch]                                      ;#12E5: 8E 06 2C 00
        mov     ah, 4Ah                                        ;#12E9: B4 4A
        int     21h                                            ;#12EB: CD 21
        pop     bx                                             ;#12ED: 5B
        jnb     short 130Ah                                    ;#12EE: 73 1A
        mov     ah, 48h                                        ;#12F0: B4 48
        int     21h                                            ;#12F2: CD 21
        jb      short 130Ah                                    ;#12F4: 72 14
        push    es                                             ;#12F6: 06
        pop     ds                                             ;#12F7: 1F
        mov     es, ax                                         ;#12F8: 8E C0
        xor     si, si                                         ;#12FA: 33 F6
        xor     di, di                                         ;#12FC: 33 FF
        rep     movsb                                          ;#12FE: F3 A4
        mov     [cs:2Ch], ax                                   ;#1300: 2E A3 2C 00
        push    ds                                             ;#1304: 1E
        pop     es                                             ;#1305: 07
        mov     ah, 49h                                        ;#1306: B4 49
        int     21h                                            ;#1308: CD 21
        jmp     near 0E99h                                     ;#130A: E9 8C FB
        db      19 dup (0)

MSG_COMSPEC_COMMAND_COM:
        ; "COMSPEC=\COMMAND.COM"
        ; Format: FORMAT_STRING
        db      "COMSPEC=", 5Ch, "COMMAND.COM"                 ;#1320: 43 4F 4D 53 50 45 43 3D 5C 43 4F 4D 4D 41 4E 44 2E 43 4F 4D
        db      140 dup (0)
        aad     0DDh                                           ;#13C0: D5 DD

MSG_VERSAO_INCORRETA_DE_SISTEMA:
        ; "Versão incorreta de sistema.."
        ; Format: FORMAT_STRING
        db      "Versão incorreta de sistema.", 7              ;#13C2: 56 65 72 73 84 6F 20 69 6E 63 6F 72 72 65 74 61 20 64 65 20 73 69 73 74 65 6D 61 2E 07
        aad     0FFh                                           ;#13DF: D5 FF
        aad     0DDh                                           ;#13E1: D5 DD
        db      0C5h                                           ;#13E3: C5

MSG_INCONSISTENTE:
        ; " inconsistente.."
        ; Format: FORMAT_STRING
        db      " inconsistente.", 7                           ;#13E4: 20 69 6E 63 6F 6E 73 69 73 74 65 6E 74 65 2E 07
        aad     0FFh                                           ;#13F4: D5 FF
        aad     0DDh                                           ;#13F6: D5 DD

MSG_CAMINHO_PARA:
        ; "Caminho para "
        ; Format: FORMAT_STRING
        db      "Caminho para "                                ;#13F8: 43 61 6D 69 6E 68 6F 20 70 61 72 61 20
        lds     ax, di                                         ;#1405: C5 C7
        pop     es                                             ;#1407: 2E 07
        aad     0FFh                                           ;#1409: D5 FF
        aad     0DDh                                           ;#140B: D5 DD

MSG_TAMANHO_DO_CONTEXTO:
        ; "Tamanho. do contexto...."
        ; Format: FORMAT_STRING
        db      "Tamanho", 0C7h, " do contexto.", 7, 0D5h, 0FFh ;#140D: 54 61 6D 61 6E 68 6F C7 20 64 6F 20 63 6F 6E 74 65 78 74 6F 2E 07 D5 FF

MSG_OS_DIREITOS_DE_PROPRIEDADE:
        ; "..  Os direitos de propriedade do SISNE Pl"
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "  Os direitos de propriedade do SISNE Plus estão " ;#1425: 0D 0A 20 20 4F 73 20 64 69 72 65 69 74 6F 73 20 64 65 20 70 72 6F 70 72 69 65 64 61 64 65 20 64 6F 20 53 49 53 4E 45 20 50 6C 75 73 20 65 73 74 84 6F 20

MSG_RESERVADOS_ITAUTEC_SCOPUS:
        ; "reservados a ITAUTEC e SCOPUS..."
        ; Format: FORMAT_STRING
        db      "reservados a ITAUTEC e SCOPUS.", 0Dh, 0Ah     ;#1458: 72 65 73 65 72 76 61 64 6F 73 20 61 20 49 54 41 55 54 45 43 20 65 20 53 43 4F 50 55 53 2E 0D 0A
        inc     word [bx+si]                                   ;#1478: FF 00
        add     bh, bh                                         ;#147A: 00 FF
        add     al, [bx+di]                                    ;#147C: 02 01
        add     [bx+si], al                                    ;#147E: 00 00
        add     [bx+si], al                                    ;#1480: 00 00
        add     [bx+si], al                                    ;#1482: 00 00

MSG_COMMAND_COM_2:
        ; "\COMMAND.COM"
        ; Format: FORMAT_STRING
        db      5Ch, "COMMAND.COM"                             ;#1484: 5C 43 4F 4D 4D 41 4E 44 2E 43 4F 4D
        add     [bx+si], al                                    ;#1490: 00 00
        add     [bx+si], al                                    ;#1492: 00 00
        add     [bp+di+2C3Eh], al                              ;#1494: 00 83 3E 2C
        add     [bx+si], al                                    ;#1498: 00 00
        jz      short 14ABh                                    ;#149A: 74 0F
        dec     byte [147Dh]                                   ;#149C: FE 0E 7D 14
        push    ds                                             ;#14A0: 1E
        call    near 0DDFh                                     ;#14A1: E8 3B F9
        pop     ds                                             ;#14A4: 1F
        jb      short 14ABh                                    ;#14A5: 72 04
        mov     [147Eh], si                                    ;#14A7: 89 36 7E 14
        ret                                                    ;#14AB: C3
        call    near 0C31h                                     ;#14AC: E8 82 F7
        mov     [28Ch], dx                                     ;#14AF: 89 16 8C 02
        call    near 0C1Eh                                     ;#14B3: E8 68 F7
        mov     ah, 30h                                        ;#14B6: B4 30
        int     21h                                            ;#14B8: CD 21
        xchg    al, ah                                         ;#14BA: 86 E0
        cmp     ax, 31Eh                                       ;#14BC: 3D 1E 03
        jnb     short 14C4h                                    ;#14BF: 73 03
        jmp     near 1545h                                     ;#14C1: E9 81 00
        add     [0B35h], ah                                    ;#14C4: 00 26 35 0B
        aam                                                    ;#14C8: D4 0A
        xchg    ah, al                                         ;#14CA: 86 C4
        add     [0B37h], ax                                    ;#14CC: 01 06 37 0B
        mov     ax, 1808h                                      ;#14D0: B8 08 18
        int     21h                                            ;#14D3: CD 21
        or      al, al                                         ;#14D5: 0A C0
        jz      short 1545h                                    ;#14D7: 74 6C
        or      ah, ah                                         ;#14D9: 0A E4
        jz      short 14E9h                                    ;#14DB: 74 0C
        mov     byte [0B3Bh], 50h                              ;#14DD: C6 06 3B 0B 50
        add     ah, 60h                                        ;#14E2: 80 C4 60
        mov     [0B3Eh], ah                                    ;#14E5: 88 26 3E 0B
        dec     al                                             ;#14E9: FE C8
        aam                                                    ;#14EB: D4 0A
        xchg    ah, al                                         ;#14ED: 86 C4
        add     [0B3Ch], ax                                    ;#14EF: 01 06 3C 0B
        mov     ax, 1815h                                      ;#14F3: B8 15 18
        int     21h                                            ;#14F6: CD 21
        cmp     al, 2                                          ;#14F8: 3C 02
        jnz     short 1501h                                    ;#14FA: 75 05
        mov     byte [147Bh], 0                                ;#14FC: C6 06 7B 14 00
        call    near 0B81h                                     ;#1501: E8 7D F6
        mov     [1479h], ax                                    ;#1504: A3 79 14
        push    es                                             ;#1507: 06
        mov     ax, 352Eh                                      ;#1508: B8 2E 35
        int     21h                                            ;#150B: CD 21
        mov     si, COMMAND_ENTRY                              ;#150D: BE 00 01
        mov     di, si                                         ;#1510: 8B FE
        mov     cx, SEGMENT_FIXUP_TABLE                        ;#1512: B9 31 01
        sub     cx, si                                         ;#1515: 2B CE
        rep     cmpsb                                          ;#1517: F3 A6
        mov     al, [es:276h]                                  ;#1519: 26 A0 76 02
        pop     es                                             ;#151D: 07
        jnz     short 152Ch                                    ;#151E: 75 0C
        mov     byte [147Bh], 0                                ;#1520: C6 06 7B 14 00
        or      al, al                                         ;#1525: 0A C0
        jz      short 152Ch                                    ;#1527: 74 03
        call    near 15C1h                                     ;#1529: E8 95 00
        mov     ax, cs                                         ;#152C: 8C C8
        cmp     [16h], ax                                      ;#152E: 39 06 16 00
        jnz     short 1537h                                    ;#1532: 75 03
        call    near 15D5h                                     ;#1534: E8 9E 00
        cmp     word [COMMAND_ENTRY], 4BEBh                    ;#1537: 81 3E 00 01 EB 4B
        jnz     short 1540h                                    ;#153D: 75 01
        ret                                                    ;#153F: C3
        mov     dx, 13E1h                                      ;#1540: BA E1 13
        jmp     short 1548h                                    ;#1543: EB 03
        mov     dx, 13C0h                                      ;#1545: BA C0 13
        call    near 0E6Dh                                     ;#1548: E8 22 F9
        mov     ax, cs                                         ;#154B: 8C C8
        cmp     [16h], ax                                      ;#154D: 39 06 16 00
        jz      short 1551h                                    ;#1551: 74 FE
        int     20h                                            ;#1553: CD 20
        mov     di, PIPE_TEMP_NAME_1                           ;#1555: BF CC 04
        call    near 155Eh                                     ;#1558: E8 03 00
        mov     di, PIPE_TEMP_NAME_2                           ;#155B: BF DC 04
        mov     cx, 0Bh                                        ;#155E: B9 0B 00
        mov     ax, 3A20h                                      ;#1561: B8 20 3A
        stosw                                                  ;#1564: AB
        mov     ax, 2Fh                                        ;#1565: B8 2F 00
        stosw                                                  ;#1568: AB
        mov     al, 5Fh                                        ;#1569: B0 5F
        rep     stosb                                          ;#156B: F3 AA
        mov     al, 2Eh                                        ;#156D: B0 2E
        mov     [es:di-4], al                                  ;#156F: 26 88 45 FC
        xor     al, al                                         ;#1573: 32 C0
        stosb                                                  ;#1575: AA
        ret                                                    ;#1576: C3
        push    dx                                             ;#1577: 52
        push    cx                                             ;#1578: 51
        xor     dx, dx                                         ;#1579: 33 D2
        call    near 173Ch                                     ;#157B: E8 BE 01
        call    near 1726h                                     ;#157E: E8 A5 01
        jb      short 159Fh                                    ;#1581: 72 1C
        cmp     dx, 1999h                                      ;#1583: 81 FA 99 19
        jnbe    short 159Ah                                    ;#1587: 77 11
        sub     al, 30h                                        ;#1589: 2C 30
        cbw                                                    ;#158B: 98
        shl     dx, 1                                          ;#158C: D1 E2
        mov     cx, dx                                         ;#158E: 8B CA
        shl     dx, 1                                          ;#1590: D1 E2
        shl     dx, 1                                          ;#1592: D1 E2
        add     dx, cx                                         ;#1594: 03 D1
        add     dx, ax                                         ;#1596: 03 D0
        jnb     short 157Bh                                    ;#1598: 73 E1
        mov     dx, 0FFFFh                                     ;#159A: BA FF FF
        jmp     short 157Bh                                    ;#159D: EB DC
        mov     ax, 0A0h                                       ;#159F: B8 A0 00
        cmp     dx, ax                                         ;#15A2: 3B D0
        jb      short 15B4h                                    ;#15A4: 72 0E
        mov     ax, 8000h                                      ;#15A6: B8 00 80
        cmp     dx, ax                                         ;#15A9: 3B D0
        jnbe    short 15B4h                                    ;#15AB: 77 07
        mov     ax, dx                                         ;#15AD: 8B C2
        add     ax, 0Fh                                        ;#15AF: 05 0F 00
        jmp     short 15BAh                                    ;#15B2: EB 06
        mov     dx, 140Bh                                      ;#15B4: BA 0B 14
        call    near 0E44h                                     ;#15B7: E8 8A F8
        mov     cl, 4                                          ;#15BA: B1 04
        shr     ax, cl                                         ;#15BC: D3 E8
        pop     cx                                             ;#15BE: 59
        pop     dx                                             ;#15BF: 5A
        ret                                                    ;#15C0: C3
        mov     [276h], al                                     ;#15C1: A2 76 02
        mov     [3EDh], al                                     ;#15C4: A2 ED 03
        ret                                                    ;#15C7: C3
        mov     [289h], si                                     ;#15C8: 89 36 89 02
        mov     byte [147Ch], 1                                ;#15CC: C6 06 7C 14 01
        pop     ax                                             ;#15D1: 58
        jmp     near 1773h                                     ;#15D2: E9 9E 01
        mov     byte [277h], 1                                 ;#15D5: C6 06 77 02 01
        and     byte [147Ch], 1                                ;#15DA: 80 26 7C 14 01
        ret                                                    ;#15DF: C3
        mov     byte [147Ch], 1                                ;#15E0: C6 06 7C 14 01
        ret                                                    ;#15E5: C3
        mov     byte [279h], 0                                 ;#15E6: C6 06 79 02 00
        ret                                                    ;#15EB: C3
        mov     byte [147Bh], 0                                ;#15EC: C6 06 7B 14 00
        ret                                                    ;#15F1: C3
        call    near 173Ch                                     ;#15F2: E8 47 01

MSG_15F5:
        ; "r.<:u"
        ; Format: FORMAT_STRING
        db      "r", 0Ah, "<:u"                                ;#15F5: 72 0A 3C 3A 75
        push    es                                             ;#15FA: 06
        call    near 1577h                                     ;#15FB: E8 79 FF
        mov     [1480h], ax                                    ;#15FE: A3 80 14
        dec     si                                             ;#1601: 4E
        ret                                                    ;#1602: C3
        cmp     al, [1479h]                                    ;#1603: 3A 06 79 14
        jnz     short 162Fh                                    ;#1607: 75 26
        call    near 173Ch                                     ;#1609: E8 30 01
        jb      short 1601h                                    ;#160C: 72 F3
        call    near 1726h                                     ;#160E: E8 15 01
        jnb     short 15C1h                                    ;#1611: 73 AE
        call    near 171Bh                                     ;#1613: E8 05 01
        cmp     al, 43h                                        ;#1616: 3C 43
        jz      short 15C8h                                    ;#1618: 74 AE
        cmp     al, 50h                                        ;#161A: 3C 50
        jz      short 15D5h                                    ;#161C: 74 B7
        cmp     al, 44h                                        ;#161E: 3C 44
        jz      short 15E0h                                    ;#1620: 74 BE
        cmp     al, 4Fh                                        ;#1622: 3C 4F
        jz      short 15E6h                                    ;#1624: 74 C0
        cmp     al, 4Dh                                        ;#1626: 3C 4D
        jz      short 15ECh                                    ;#1628: 74 C2
        cmp     al, 45h                                        ;#162A: 3C 45
        jz      short 15F2h                                    ;#162C: 74 C4
        ret                                                    ;#162E: C3
        dec     si                                             ;#162F: 4E
        mov     di, 2020h                                      ;#1630: BF 20 20
        mov     dx, di                                         ;#1633: 8B D7
        call    near 173Ch                                     ;#1635: E8 04 01
        jz      short 1646h                                    ;#1638: 74 0C
        cmp     di, 2063h                                      ;#163A: 81 FF 63 20
        jnb     short 1635h                                    ;#163E: 73 F5
        call    near 171Bh                                     ;#1640: E8 D8 00
        stosb                                                  ;#1643: AA
        jmp     short 1635h                                    ;#1644: EB EF
        dec     si                                             ;#1646: 4E
        db      81h                                            ;#1647: 81
        db      0FFh                                           ;#1648: FF

MSG_SFC:
        ; "c sFÇ}"
        ; Format: FORMAT_STRING
        db      "c sFÇ}"                                       ;#1649: 63 20 73 46 80 7D
        db      0FFh                                           ;#164F: FF
        cmp     dh, [di+7]                                     ;#1650: 3A 75 07
        cmp     di, 2022h                                      ;#1653: 81 FF 22 20
        jz      short 165Ah                                    ;#1657: 74 01
        dec     di                                             ;#1659: 4F
        mov     byte [di], 0                                   ;#165A: C6 05 00
        call    near 0C4Fh                                     ;#165D: E8 EF F5
        jnb     short 1692h                                    ;#1660: 73 30
        mov     byte [147Dh], 2                                ;#1662: C6 06 7D 14 02
        push    si                                             ;#1667: 56
        mov     si, MSG_COMMAND_COM_2                          ;#1668: BE 84 14
        mov     cx, 0Dh                                        ;#166B: B9 0D 00
        dec     di                                             ;#166E: 4F
        mov     al, [di]                                       ;#166F: 8A 05
        cmp     al, [147Ah]                                    ;#1671: 3A 06 7A 14
        jz      short 167Ch                                    ;#1675: 74 05
        cmp     al, 5Ch                                        ;#1677: 3C 5C
        jz      short 167Ch                                    ;#1679: 74 01
        inc     di                                             ;#167B: 47
        rep     movsb                                          ;#167C: F3 A4
        pop     si                                             ;#167E: 5E
        mov     dx, 2020h                                      ;#167F: BA 20 20
        call    near 172Eh                                     ;#1682: E8 A9 00
        jb      short 1693h                                    ;#1685: 72 0C
        xchg    dx, si                                         ;#1687: 87 F2
        mov     di, 1328h                                      ;#1689: BF 28 13
        call    near 1714h                                     ;#168C: E8 85 00
        stosb                                                  ;#168F: AA
        xchg    dx, si                                         ;#1690: 87 F2
        ret                                                    ;#1692: C3
        mov     dx, 13F6h                                      ;#1693: BA F6 13
        jmp     near 0E44h                                     ;#1696: E9 AB F7
        cmp     byte [147Dh], 1                                ;#1699: 80 3E 7D 14 01
        jnb     short 16AEh                                    ;#169E: 73 0E
        mov     si, [147Eh]                                    ;#16A0: 8B 36 7E 14
        or      si, si                                         ;#16A4: 0B F6
        jz      short 16D9h                                    ;#16A6: 74 31
        mov     ds, [2Ch]                                      ;#16A8: 8E 1E 2C 00
        jmp     short 16DCh                                    ;#16AC: EB 2E
        pushf                                                  ;#16AE: 9C
        mov     ax, MSG_COMSPEC_COMMAND_COM                    ;#16AF: B8 20 13
        mov     cl, 4                                          ;#16B2: B1 04
        shr     ax, cl                                         ;#16B4: D3 E8
        mov     cx, ax                                         ;#16B6: 8B C8
        mov     ax, ds                                         ;#16B8: 8C D8
        add     ax, cx                                         ;#16BA: 03 C1
        mov     [2Ch], ax                                      ;#16BC: A3 2C 00
        popf                                                   ;#16BF: 9D
        jnbe    short 16D9h                                    ;#16C0: 77 17
        mov     al, [5Ch]                                      ;#16C2: A0 5C 00
        or      al, al                                         ;#16C5: 0A C0
        jz      short 16D9h                                    ;#16C7: 74 10
        mov     si, MSG_COMMAND_COM_2                          ;#16C9: BE 84 14
        mov     di, 1328h                                      ;#16CC: BF 28 13
        mov     cx, 0Dh                                        ;#16CF: B9 0D 00
        add     al, 40h                                        ;#16D2: 04 40
        mov     ah, 3Ah                                        ;#16D4: B4 3A
        stosw                                                  ;#16D6: AB
        rep     movsb                                          ;#16D7: F3 A4
        mov     si, 1328h                                      ;#16D9: BE 28 13
        mov     di, 200h                                       ;#16DC: BF 00 02
        call    near 1714h                                     ;#16DF: E8 32 00
        push    es                                             ;#16E2: 06
        pop     ds                                             ;#16E3: 1F
        mov     es, [2Ch]                                      ;#16E4: 8E 06 2C 00
        xor     di, di                                         ;#16E8: 33 FF
        mov     cx, 8000h                                      ;#16EA: B9 00 80
        xor     al, al                                         ;#16ED: 32 C0
        repne   scasb                                          ;#16EF: F2 AE
        scasb                                                  ;#16F1: AE
        jnz     short 16EFh                                    ;#16F2: 75 FB
        push    ds                                             ;#16F4: 1E
        pop     es                                             ;#16F5: 07
        mov     [1482h], di                                    ;#16F6: 89 3E 82 14
        add     di, 8Fh                                        ;#16FA: 81 C7 8F 00
        and     di, 0FFF0h                                     ;#16FE: 81 E7 F0 FF
        mov     ax, [1480h]                                    ;#1702: A1 80 14
        mov     cl, 4                                          ;#1705: B1 04
        shl     ax, cl                                         ;#1707: D3 E0
        cmp     di, ax                                         ;#1709: 3B F8
        jbe     short 1713h                                    ;#170B: 76 06
        shr     di, cl                                         ;#170D: D3 EF
        mov     [1480h], di                                    ;#170F: 89 3E 80 14
        ret                                                    ;#1713: C3
        lodsb                                                  ;#1714: AC
        stosb                                                  ;#1715: AA
        or      al, al                                         ;#1716: 0A C0
        jnz     short 1714h                                    ;#1718: 75 FA
        ret                                                    ;#171A: C3
        cmp     al, 61h                                        ;#171B: 3C 61
        jb      short 1725h                                    ;#171D: 72 06
        cmp     al, 7Ah                                        ;#171F: 3C 7A
        jnbe    short 1725h                                    ;#1721: 77 02
        and     al, 0DFh                                       ;#1723: 24 DF
        ret                                                    ;#1725: C3
        cmp     al, 30h                                        ;#1726: 3C 30
        jb      short 172Dh                                    ;#1728: 72 03
        cmp     al, 3Ah                                        ;#172A: 3C 3A
        cmc                                                    ;#172C: F5
        ret                                                    ;#172D: C3
        mov     ax, 3D00h                                      ;#172E: B8 00 3D
        int     21h                                            ;#1731: CD 21
        jb      short 173Bh                                    ;#1733: 72 06
        mov     bx, ax                                         ;#1735: 8B D8
        mov     ah, 3Eh                                        ;#1737: B4 3E
        int     21h                                            ;#1739: CD 21
        ret                                                    ;#173B: C3
        lodsb                                                  ;#173C: AC
        cmp     al, 0Dh                                        ;#173D: 3C 0D
        stc                                                    ;#173F: F9

MSG_1740:
        ; "t.< t"
        ; Format: FORMAT_STRING
        db      "t", 7, "< t"                                  ;#1740: 74 07 3C 20 74
        add     bh, [si]                                       ;#1745: 02 3C
        or      ax, di                                         ;#1747: 09 F8
        ret                                                    ;#1749: C3
        call    near 1495h                                     ;#174A: E8 48 FD
        call    near 14ACh                                     ;#174D: E8 5C FD
        call    near 1555h                                     ;#1750: E8 02 FE
        mov     si, 80h                                        ;#1753: BE 80 00
        lodsb                                                  ;#1756: AC
        mov     ah, 7Eh                                        ;#1757: B4 7E
        cmp     al, ah                                         ;#1759: 3A C4
        jbe     short 175Fh                                    ;#175B: 76 02
        mov     al, ah                                         ;#175D: 8A C4
        push    si                                             ;#175F: 56
        cbw                                                    ;#1760: 98
        add     si, ax                                         ;#1761: 03 F0
        mov     byte [si], 0Dh                                 ;#1763: C6 04 0D
        pop     si                                             ;#1766: 5E
        call    near 173Ch                                     ;#1767: E8 D2 FF
        jb      short 1773h                                    ;#176A: 72 07
        jz      short 1767h                                    ;#176C: 74 F9
        call    near 1603h                                     ;#176E: E8 92 FE
        jmp     short 1767h                                    ;#1771: EB F4
        call    near 1699h                                     ;#1773: E8 23 FF
        push    cs                                             ;#1776: 0E
        pop     ds                                             ;#1777: 1F
        mov     ah, 19h                                        ;#1778: B4 19
        int     21h                                            ;#177A: CD 21
        add     al, 41h                                        ;#177C: 04 41
        mov     [AUTOEXEC_PATH], al                            ;#177E: A2 E3 03
        mov     ax, [200h]                                     ;#1781: A1 00 02
        cmp     ah, 3Ah                                        ;#1784: 80 FC 3A
        jnz     short 178Ch                                    ;#1787: 75 03
        mov     [AUTOEXEC_PATH], al                            ;#1789: A2 E3 03
        push    es                                             ;#178C: 06
        mov     es, [252h]                                     ;#178D: 8E 06 52 02
        mov     cx, 4E70h                                      ;#1791: B9 70 4E
        mov     si, 6F8Eh                                      ;#1794: BE 8E 6F
        mov     di, 4F6Eh                                      ;#1797: BF 6E 4F
        shr     cx, 1                                          ;#179A: D1 E9
        std                                                    ;#179C: FD
        rep     movsw                                          ;#179D: F3 A5
        cld                                                    ;#179F: FC
        pop     es                                             ;#17A0: 07
        call    near 0B93h                                     ;#17A1: E8 EF F3
        mov     [254h], ax                                     ;#17A4: A3 54 02
        call    near 0B62h                                     ;#17A7: E8 B8 F3
        mov     si, 0Ah                                        ;#17AA: BE 0A 00
        mov     di, 256h                                       ;#17AD: BF 56 02
        mov     cx, 7                                          ;#17B0: B9 07 00
        rep     movsw                                          ;#17B3: F3 A5
        mov     si, 264h                                       ;#17B5: BE 64 02
        mov     di, 0Ah                                        ;#17B8: BF 0A 00
        mov     cx, 7                                          ;#17BB: B9 07 00
        rep     movsw                                          ;#17BE: F3 A5
        cmp     byte [277h], 0                                 ;#17C0: 80 3E 77 02 00
        jz      short 17DAh                                    ;#17C5: 74 13
        mov     si, 0Ah                                        ;#17C7: BE 0A 00
        mov     di, 256h                                       ;#17CA: BF 56 02
        mov     cx, 7                                          ;#17CD: B9 07 00
        rep     movsw                                          ;#17D0: F3 A5
        mov     dx, 1242h                                      ;#17D2: BA 42 12
        mov     ax, 252Eh                                      ;#17D5: B8 2E 25
        int     21h                                            ;#17D8: CD 21
        mov     bx, 1310h                                      ;#17DA: BB 10 13
        mov     cl, 4                                          ;#17DD: B1 04
        shr     bx, cl                                         ;#17DF: D3 EB
        mov     ah, 4Ah                                        ;#17E1: B4 4A
        int     21h                                            ;#17E3: CD 21
        cmp     byte [147Dh], 0                                ;#17E5: 80 3E 7D 14 00
        jz      short 1804h                                    ;#17EA: 74 18
        mov     bx, 0Ah                                        ;#17EC: BB 0A 00
        mov     ah, 48h                                        ;#17EF: B4 48
        int     21h                                            ;#17F1: CD 21
        mov     si, MSG_COMSPEC_COMMAND_COM                    ;#17F3: BE 20 13
        push    es                                             ;#17F6: 06
        mov     es, ax                                         ;#17F7: 8E C0
        xor     di, di                                         ;#17F9: 33 FF
        mov     cx, 50h                                        ;#17FB: B9 50 00
        rep     movsw                                          ;#17FE: F3 A5
        pop     es                                             ;#1800: 07
        mov     [2Ch], ax                                      ;#1801: A3 2C 00
        cmp     byte [147Ch], 0                                ;#1804: 80 3E 7C 14 00
        jnz     short 181Ah                                    ;#1809: 75 0F
        mov     dx, AUTOEXEC_PATH                              ;#180B: BA E3 03
        call    near 172Eh                                     ;#180E: E8 1D FF
        jb      short 181Ah                                    ;#1811: 72 07
        or      byte [339h], 4                                 ;#1813: 80 0E 39 03 04
        jmp     short 1821h                                    ;#1818: EB 07
        cmp     word [289h], 0                                 ;#181A: 83 3E 89 02 00

MSG_UNC:
        ; "uNÇ>{"
        ; Format: FORMAT_STRING
        db      "uNÇ>{"                                        ;#181F: 75 4E 80 3E 7B
        adc     al, 0                                          ;#1824: 14 00
        jz      short 1847h                                    ;#1826: 74 1F
        mov     word [1491h], 122h                             ;#1828: C7 06 91 14 22 01
        mov     [1493h], cs                                    ;#182E: 8C 0E 93 14
        mov     ax, MONTH_NAME_TABLE                           ;#1832: B8 90 18
        shr     ax, 1                                          ;#1835: D1 E8
        shr     ax, 1                                          ;#1837: D1 E8
        shr     ax, 1                                          ;#1839: D1 E8
        shr     ax, 1                                          ;#183B: D1 E8
        add     [1493h], ax                                    ;#183D: 01 06 93 14
        call    far word [1491h]                               ;#1841: FF 1E 91 14
        jmp     short 186Fh                                    ;#1845: EB 28
        mov     ah, 40h                                        ;#1847: B4 40
        mov     bx, 1                                          ;#1849: BB 01 00
        mov     dx, 1882h                                      ;#184C: BA 82 18
        mov     cx, 1                                          ;#184F: B9 01 00
        int     21h                                            ;#1852: CD 21
        mov     dx, MSG_OS_DIREITOS_DE_PROPRIEDADE             ;#1854: BA 25 14
        call    near 0E6Dh                                     ;#1857: E8 13 F6
        call    near 187Ah                                     ;#185A: E8 1D 00
        mov     dx, MSG_SISNE_PLUS                             ;#185D: BA 26 0B
        call    near 187Dh                                     ;#1860: E8 1A 00
        call    near 187Ah                                     ;#1863: E8 14 00
        mov     dx, 0B48h                                      ;#1866: BA 48 0B
        call    near 187Dh                                     ;#1869: E8 11 00
        call    near 187Ah                                     ;#186C: E8 0B 00
        mov     bx, [1480h]                                    ;#186F: 8B 1E 80 14
        mov     cx, [1482h]                                    ;#1873: 8B 0E 82 14
        jmp     near 12E3h                                     ;#1877: E9 69 FA
        mov     dx, 1882h                                      ;#187A: BA 82 18
        mov     ah, 9                                          ;#187D: B4 09
        int     21h                                            ;#187F: CD 21
        ret                                                    ;#1881: C3
        or      ax, 240Ah                                      ;#1882: 0D 0A 24
        db      11 dup (0)

MONTH_NAME_TABLE:
        ; Twelve 3-letter month abbreviations, JAN..DEZ
        ; Format: FORMAT_HEX
        ; raw
        db      4Ah, 41h, 4Eh, 46h                             ;#1890
        db      45h, 56h, 4Dh, 41h                             ;#1894
        db      52h, 41h, 42h, 52h                             ;#1898
        db      4Dh, 41h, 49h, 4Ah                             ;#189C
        db      55h, 4Eh, 4Ah, 55h                             ;#18A0
        db      4Ch, 41h, 47h, 4Fh                             ;#18A4
        db      53h, 45h, 54h, 4Fh                             ;#18A8
        db      55h, 54h, 4Eh, 4Fh                             ;#18AC
        db      56h, 44h, 45h, 5Ah                             ;#18B0

DAY_NAME_TABLE:
        ; Seven 7-character weekday names, DOMINGO..SABADO, blank-padded
        ; Format: FORMAT_HEX
        ; raw
        db      44h, 4Fh, 4Dh, 49h                             ;#18B4
        db      4Eh, 47h, 4Fh, 53h                             ;#18B8
        db      45h, 47h, 55h, 4Eh                             ;#18BC
        db      44h, 41h, 20h, 54h                             ;#18C0
        db      45h, 52h, 80h, 41h                             ;#18C4
        db      20h, 51h, 55h, 41h                             ;#18C8
        db      52h, 54h, 41h, 20h                             ;#18CC
        db      51h, 55h, 49h, 4Eh                             ;#18D0
        db      54h, 41h, 20h, 20h                             ;#18D4
        db      53h, 45h, 58h, 54h                             ;#18D8
        db      41h, 20h, 53h, 41h                             ;#18DC
        db      42h, 41h, 44h, 4Fh                             ;#18E0
        db      20h                                            ;#18E4
        mov     dh, 15h                                        ;#18E5: B6 15
        mov     ah, 2                                          ;#18E7: B4 02
        mov     bh, 0                                          ;#18E9: B7 00
        int     10h                                            ;#18EB: CD 10
        ret                                                    ;#18ED: C3
        mov     si, ax                                         ;#18EE: 8B F0
        call    near 18E5h                                     ;#18F0: E8 F2 FF
        mov     ax, si                                         ;#18F3: 8B C6
        cbw                                                    ;#18F5: 98
        mov     dl, 0Ah                                        ;#18F6: B2 0A
        div     dl                                             ;#18F8: F6 F2
        add     ax, 3030h                                      ;#18FA: 05 30 30
        mov     dl, ah                                         ;#18FD: 8A D4
        mov     ah, 0Eh                                        ;#18FF: B4 0E
        mov     bh, 0                                          ;#1901: B7 00
        int     10h                                            ;#1903: CD 10
        mov     ah, 0Eh                                        ;#1905: B4 0E
        mov     al, dl                                         ;#1907: 8A C2
        int     10h                                            ;#1909: CD 10
        ret                                                    ;#190B: C3
        call    near 18E5h                                     ;#190C: E8 D6 FF
        mov     bh, 0                                          ;#190F: B7 00
        lodsb                                                  ;#1911: AC
        mov     ah, 0Eh                                        ;#1912: B4 0E
        int     10h                                            ;#1914: CD 10
        loop    1911h                                          ;#1916: E2 F9
        ret                                                    ;#1918: C3
        mov     dx, 0                                          ;#1919: BA 00 00
        call    near 18E7h                                     ;#191C: E8 C8 FF
        mov     cx, 0                                          ;#191F: B9 00 00
        mov     dh, 18h                                        ;#1922: B6 18
        mov     dl, 4Fh                                        ;#1924: B2 4F
        mov     ax, 600h                                       ;#1926: B8 00 06
        mov     bh, 7                                          ;#1929: B7 07
        int     10h                                            ;#192B: CD 10
        call    near 19BEh                                     ;#192D: E8 8E 00
        mov     ah, 2Ch                                        ;#1930: B4 2C
        int     21h                                            ;#1932: CD 21
        push    dx                                             ;#1934: 52
        mov     al, ch                                         ;#1935: 8A C5
        mov     dl, 5                                          ;#1937: B2 05
        call    near 18EEh                                     ;#1939: E8 B2 FF
        mov     al, cl                                         ;#193C: 8A C1
        mov     dl, 8                                          ;#193E: B2 08
        call    near 18EEh                                     ;#1940: E8 AB FF
        pop     ax                                             ;#1943: 58
        mov     al, ah                                         ;#1944: 8A C4
        mov     dl, 0Bh                                        ;#1946: B2 0B
        call    near 18EEh                                     ;#1948: E8 A3 FF
        mov     ah, 2Ah                                        ;#194B: B4 2A
        int     21h                                            ;#194D: CD 21
        push    ax                                             ;#194F: 50
        push    cx                                             ;#1950: 51
        dec     dh                                             ;#1951: FE CE
        mov     bl, dh                                         ;#1953: 8A DE
        mov     al, dl                                         ;#1955: 8A C2
        mov     dl, 31h                                        ;#1957: B2 31
        call    near 18EEh                                     ;#1959: E8 92 FF
        mov     dh, bl                                         ;#195C: 8A F3
        shl     bl, 1                                          ;#195E: D0 E3
        add     bl, dh                                         ;#1960: 02 DE
        xor     bh, bh                                         ;#1962: 32 FF
        lea     si, [bx+0]                                     ;#1964: 8D B7 00 00
        mov     dl, 34h                                        ;#1968: B2 34
        mov     cx, 3                                          ;#196A: B9 03 00
        cld                                                    ;#196D: FC
        call    near 190Ch                                     ;#196E: E8 9B FF
        pop     ax                                             ;#1971: 58
        mov     dl, 64h                                        ;#1972: B2 64
        div     dl                                             ;#1974: F6 F2
        mov     cl, ah                                         ;#1976: 8A CC
        mov     dl, 38h                                        ;#1978: B2 38
        call    near 18EEh                                     ;#197A: E8 71 FF
        mov     al, cl                                         ;#197D: 8A C1
        call    near 18F5h                                     ;#197F: E8 73 FF
        pop     ax                                             ;#1982: 58
        mov     cx, 7                                          ;#1983: B9 07 00
        mul     cl                                             ;#1986: F6 E1
        mov     bx, ax                                         ;#1988: 8B D8
        lea     si, [bx+24h]                                   ;#198A: 8D B7 24 00
        mov     dl, 44h                                        ;#198E: B2 44
        call    near 190Ch                                     ;#1990: E8 79 FF
        push    ds                                             ;#1993: 1E
        push    ss                                             ;#1994: 16
        pop     ds                                             ;#1995: 1F
        mov     cx, 9                                          ;#1996: B9 09 00
        cmp     byte [0B3Eh], 24h                              ;#1999: 80 3E 3E 0B 24
        jz      short 19A1h                                    ;#199E: 74 01
        inc     cx                                             ;#19A0: 41
        mov     dl, 20h                                        ;#19A1: B2 20
        mov     si, 0B35h                                      ;#19A3: BE 35 0B
        call    near 190Ch                                     ;#19A6: E8 63 FF
        pop     ds                                             ;#19A9: 1F
        mov     dh, 16h                                        ;#19AA: B6 16
        mov     dl, 0                                          ;#19AC: B2 00
        call    near 18E7h                                     ;#19AE: E8 36 FF
        ret                                                    ;#19B1: C3
        push    ds                                             ;#19B2: 1E
        push    es                                             ;#19B3: 06
        push    cs                                             ;#19B4: 0E
        pop     ds                                             ;#19B5: 1F
        push    cs                                             ;#19B6: 0E
        pop     es                                             ;#19B7: 07
        call    near 1919h                                     ;#19B8: E8 5E FF
        pop     es                                             ;#19BB: 07
        pop     ds                                             ;#19BC: 1F
        retf                                                   ;#19BD: CB
        push    ds                                             ;#19BE: 1E
        push    si                                             ;#19BF: 56
        mov     si, cs                                         ;#19C0: 8C CE
        mov     ds, si                                         ;#19C2: 8E DE
        mov     si, 13Dh                                       ;#19C4: BE 3D 01
        call    near MSG_PSQRUW                                ;#19C7: E8 43 05
        pop     si                                             ;#19CA: 5E
        pop     ds                                             ;#19CB: 1F
        ret                                                    ;#19CC: C3
        rol     word [si], 1                                   ;#19CD: D1 04
        add     [bx+si], al                                    ;#19CF: 00 00
        push    cs                                             ;#19D1: 0E
        add     [bx+di], al                                    ;#19D2: 00 01
        add     dx, bx                                         ;#19D4: 01 DA
        add     di, di                                         ;#19D6: 03 FF
        dec     si                                             ;#19D8: 4E
        les     ax, [bp+di]                                    ;#19D9: C4 03
        add     [bp+si], ax                                    ;#19DB: 01 02
        mov     di, 0B303h                                     ;#19DD: BF 03 B3
        add     ax, [bx+di]                                    ;#19E0: 03 01
        dec     di                                             ;#19E2: 4F
        push    es                                             ;#19E3: 06
        add     [bx+di], al                                    ;#19E4: 00 01
        add     dh, [bp+di+0B303h]                             ;#19E6: 02 B3 03 B3
        add     ax, [bp+si]                                    ;#19EA: 03 02
        dec     di                                             ;#19EC: 4F
        push    es                                             ;#19ED: 06
        add     [bx+di], al                                    ;#19EE: 00 01
        add     dh, [bp+di+0B303h]                             ;#19F0: 02 B3 03 B3
        add     ax, [bp+di]                                    ;#19F4: 03 03
        or      al, [si]                                       ;#19F6: 0A 04
        add     [bx+di], al                                    ;#19F8: 00 01
        add     [307h], bp                                     ;#19FA: 01 2E 07 03
        db      0Fh                                            ;#19FE: 0F
        add     al, 0                                          ;#19FF: 04 00
        add     [bx+di], ax                                    ;#1A01: 01 01
        mov     di, 307h                                       ;#1A03: BF 07 03
        cmp     ax, [si]                                       ;#1A06: 3B 04
        add     [bx+di], al                                    ;#1A08: 00 01
        add     [307h], bp                                     ;#1A0A: 01 2E 07 03
        dec     ax                                             ;#1A0E: 48
        add     al, 0                                          ;#1A0F: 04 00
        add     [bx+di], ax                                    ;#1A11: 01 01
        mov     di, 307h                                       ;#1A13: BF 07 03
        dec     di                                             ;#1A16: 4F
        push    es                                             ;#1A17: 06
        add     [bx+di], al                                    ;#1A18: 00 01
        add     dh, [bp+di+0B303h]                             ;#1A1A: 02 B3 03 B3
        add     ax, [si]                                       ;#1A1E: 03 04
        push    es                                             ;#1A20: 06
        or      ax, 0                                          ;#1A21: 0D 00 00
        or      al, [bx]                                       ;#1A24: 0A 07
        db      0DAh                                           ;#1A26: DA
        les     ax, sp                                         ;#1A27: C4 C4
        mov     di, 0DABFh                                     ;#1A29: BF BF DA
        les     ax, sp                                         ;#1A2C: C4 C4
        mov     di, 4C5h                                       ;#1A2E: BF C5 04
        adc     dl, [bx+si]                                    ;#1A31: 12 10
        add     [bx+si], al                                    ;#1A33: 00 00
        or      ax, 0DA07h                                     ;#1A35: 0D 07 DA
        les     ax, sp                                         ;#1A38: C4 C4
        mov     di, 0C4C2h                                     ;#1A3A: BF C2 C4
        ret     0BFC4h                                         ;#1A3D: C2 C4 BF
        db      0DAh                                           ;#1A40: DA
        les     ax, sp                                         ;#1A41: C4 C4
        mov     di, 2304h                                      ;#1A43: BF 04 23
        sub     [bx+si], ax                                    ;#1A46: 29 00
        add     [0DA07h], ah                                   ;#1A48: 00 26 07 DA
        les     ax, sp                                         ;#1A4C: C4 C4
        mov     di, 0C4DAh                                     ;#1A4E: BF DA C4
        les     di, [bx+0C4DAh]                                ;#1A51: C4 BF DA C4
        les     di, [bx+0C4C2h]                                ;#1A55: C4 BF C2 C4
        les     di, [bx+0C4DAh]                                ;#1A59: C4 BF DA C4
        les     di, [bx+0C4DAh]                                ;#1A5D: C4 BF DA C4
        les     di, [bx+0DABFh]                                ;#1A61: C4 BF BF DA
        les     ax, sp                                         ;#1A65: C4 C4
        mov     di, 0C4C2h                                     ;#1A67: BF C2 C4
        les     di, [bx+0C4DAh]                                ;#1A6A: C4 BF DA C4
        les     di, [bx+4B3h]                                  ;#1A6E: C4 BF B3 04
        dec     di                                             ;#1A72: 4F
        push    es                                             ;#1A73: 06
        add     [bx+di], al                                    ;#1A74: 00 01
        add     dh, [bp+di+0B303h]                             ;#1A76: 02 B3 03 B3
        add     ax, [di]                                       ;#1A7A: 03 05
        push    es                                             ;#1A7C: 06
        or      ax, 0                                          ;#1A7D: 0D 00 00
        or      al, [bx]                                       ;#1A80: 0A 07
        db      0C0h                                           ;#1A82: C0
        les     ax, sp                                         ;#1A83: C4 C4
        mov     di, 0C0B3h                                     ;#1A85: BF B3 C0
        les     ax, sp                                         ;#1A88: C4 C4
        mov     di, 5B3h                                       ;#1A8A: BF B3 05
        adc     cl, [bx+si]                                    ;#1A8D: 12 08
        add     [bx+si], al                                    ;#1A8F: 00 00
        add     ax, 0C307h                                     ;#1A91: 05 07 C3
        les     ax, sp                                         ;#1A94: C4 C4
        db      0D9h                                           ;#1A96: D9
        mov     bl, 5                                          ;#1A97: B3 05
        sbb     [si], al                                       ;#1A99: 18 04
        add     [bx+di], al                                    ;#1A9B: 00 01
        add     [bp+di+507h], si                               ;#1A9D: 01 B3 07 05
        sbb     cl, [bx+si]                                    ;#1AA1: 1A 08
        add     [bx+si], al                                    ;#1AA3: 00 00
        add     ax, 0B307h                                     ;#1AA5: 05 07 B3
        db      0DAh                                           ;#1AA8: DA
        les     ax, sp                                         ;#1AA9: C4 C4
        mov     ah, 5                                          ;#1AAB: B4 05
        and     ax, [si]                                       ;#1AAD: 23 04
        add     [bx+di], al                                    ;#1AAF: 00 01
        add     [bp+di+507h], si                               ;#1AB1: 01 B3 07 05
        push    es                                             ;#1AB5: 26 06
        add     [bx+di], al                                    ;#1AB7: 00 01
        add     dh, [bp+di+0B307h]                             ;#1AB9: 02 B3 07 B3
        pop     es                                             ;#1ABD: 07
        add     ax, 92Ah                                       ;#1ABE: 05 2A 09
        add     [bx+si], al                                    ;#1AC1: 00 00
        push    es                                             ;#1AC3: 06
        pop     es                                             ;#1AC4: 07
        mov     bl, 0C3h                                       ;#1AC5: B3 C3
        les     ax, sp                                         ;#1AC7: C4 C4
        db      0D9h                                           ;#1AC9: D9
        mov     bl, 5                                          ;#1ACA: B3 05
        xor     cx, [bx+si]                                    ;#1ACC: 33 08
        add     [bx+si], al                                    ;#1ACE: 00 00
        add     ax, 0DA07h                                     ;#1AD0: 05 07 DA
        les     ax, sp                                         ;#1AD3: C4 C4
        mov     ah, 0B3h                                       ;#1AD5: B4 B3
        add     ax, 63Bh                                       ;#1AD7: 05 3B 06
        add     [bx+di], al                                    ;#1ADA: 00 01
        add     dh, [bp+di+0B307h]                             ;#1ADC: 02 B3 07 B3
        pop     es                                             ;#1AE0: 07
        add     ax, MSG_OU_DISPOSITIVO_AUSENTE                 ;#1AE1: 05 3F 06
        add     [bx+di], al                                    ;#1AE4: 00 01
        add     dh, [bp+di+0B307h]                             ;#1AE6: 02 B3 07 B3
        pop     es                                             ;#1AEA: 07
        add     ax, 943h                                       ;#1AEB: 05 43 09
        add     [bx+si], al                                    ;#1AEE: 00 00
        push    es                                             ;#1AF0: 06
        pop     es                                             ;#1AF1: 07
        mov     bl, 0DAh                                       ;#1AF2: B3 DA
        les     ax, sp                                         ;#1AF4: C4 C4
        mov     ah, 0B3h                                       ;#1AF6: B4 B3
        add     ax, 64Fh                                       ;#1AF8: 05 4F 06
        add     [bx+di], al                                    ;#1AFB: 00 01
        add     dh, [bp+di+0B303h]                             ;#1AFD: 02 B3 03 B3
        add     ax, [1406h]                                    ;#1B01: 03 06 06 14
        add     [bx+si], al                                    ;#1B05: 00 00
        adc     [bx], ax                                       ;#1B07: 11 07
        db      0C0h                                           ;#1B09: C0
        les     ax, sp                                         ;#1B0A: C4 C4
        db      0D9h                                           ;#1B0C: D9
        db      0C1h                                           ;#1B0D: C1
        db      0C0h                                           ;#1B0E: C0
        les     ax, sp                                         ;#1B0F: C4 C4
        db      0D9h                                           ;#1B11: D9
        db      0C0h                                           ;#1B12: C0
        les     bx, cx                                         ;#1B13: C4 D9
        db      0C0h                                           ;#1B15: C0
        les     ax, sp                                         ;#1B16: C4 C4
        db      0D9h                                           ;#1B18: D9
        db      0C1h                                           ;#1B19: C1
        push    es                                             ;#1B1A: 06
        sbb     [bp+si], cl                                    ;#1B1B: 18 0A
        add     [bx+si], al                                    ;#1B1D: 00 00
        pop     es                                             ;#1B1F: 07
        pop     es                                             ;#1B20: 07
        db      0C1h                                           ;#1B21: C1
        add     al, al                                         ;#1B22: 00 C0
        db      0C0h                                           ;#1B24: C0
        les     ax, sp                                         ;#1B25: C4 C4
        db      0C1h                                           ;#1B27: C1
        push    es                                             ;#1B28: 06
        and     dx, [bx+si]                                    ;#1B29: 23 10
        add     [bx+si], al                                    ;#1B2B: 00 00
        or      ax, 0C007h                                     ;#1B2D: 0D 07 C0
        les     ax, sp                                         ;#1B30: C4 C4
        db      0D9h                                           ;#1B32: D9
        ret                                                    ;#1B33: C3
        les     ax, sp                                         ;#1B34: C4 C4
        db      0D9h                                           ;#1B36: D9
        db      0C0h                                           ;#1B37: C0
        les     ax, sp                                         ;#1B38: C4 C4
        db      0D9h                                           ;#1B3A: D9
        db      0C1h                                           ;#1B3B: C1
        push    es                                             ;#1B3C: 06
        xor     dx, [bx+di]                                    ;#1B3D: 33 11
        add     [bx+si], al                                    ;#1B3F: 00 00
        push    cs                                             ;#1B41: 0E
        pop     es                                             ;#1B42: 07
        db      0C0h                                           ;#1B43: C0
        les     ax, sp                                         ;#1B44: C4 C4
        db      0C1h                                           ;#1B46: C1
        db      0C0h                                           ;#1B47: C0
        les     ax, sp                                         ;#1B48: C4 C4
        db      0D9h                                           ;#1B4A: D9
        db      0C1h                                           ;#1B4B: C1
        db      0C0h                                           ;#1B4C: C0
        les     ax, sp                                         ;#1B4D: C4 C4
        db      0D9h                                           ;#1B4F: D9
        db      0C1h                                           ;#1B50: C1
        push    es                                             ;#1B51: 06
        inc     bx                                             ;#1B52: 43
        or      [bx+si], ax                                    ;#1B53: 09 00
        add     [0C007h], al                                   ;#1B55: 00 06 07 C0
        db      0C0h                                           ;#1B59: C0
        les     ax, sp                                         ;#1B5A: C4 C4
        db      0D9h                                           ;#1B5C: D9
        db      0C0h                                           ;#1B5D: C0
        push    es                                             ;#1B5E: 06
        dec     di                                             ;#1B5F: 4F
        push    es                                             ;#1B60: 06
        add     [bx+di], al                                    ;#1B61: 00 01
        add     dh, [bp+di+0B303h]                             ;#1B63: 02 B3 03 B3
        add     ax, [bx]                                       ;#1B67: 03 07
        daa                                                    ;#1B69: 27
        add     al, 0                                          ;#1B6A: 04 00
        add     [bx+di], ax                                    ;#1B6C: 01 01
        db      0C1h                                           ;#1B6E: C1
        pop     es                                             ;#1B6F: 07
        pop     es                                             ;#1B70: 07
        dec     di                                             ;#1B71: 4F
        push    es                                             ;#1B72: 06
        add     [bx+di], al                                    ;#1B73: 00 01
        add     dh, [bp+di+0B303h]                             ;#1B75: 02 B3 03 B3
        add     cx, [bx+si]                                    ;#1B79: 03 08
        dec     di                                             ;#1B7B: 4F
        push    es                                             ;#1B7C: 06
        add     [bx+di], al                                    ;#1B7D: 00 01
        add     dh, [bp+di+0B303h]                             ;#1B7F: 02 B3 03 B3
        add     cx, [bx+di]                                    ;#1B83: 03 09
        db      0Fh                                            ;#1B85: 0F
        or      al, 0                                          ;#1B86: 0C 00
        add     [bx+di], ax                                    ;#1B88: 01 01
        db      0DAh                                           ;#1B8A: DA
        or      di, di                                         ;#1B8B: 0B FF
        add     ax, 0BC4h                                      ;#1B8D: 05 C4 0B
        add     [bx+di], ax                                    ;#1B90: 01 01
        mov     di, 90Bh                                       ;#1B92: BF 0B 09
        pop     ss                                             ;#1B95: 17
        push    es                                             ;#1B96: 06
        add     [bx+si], al                                    ;#1B97: 00 00
        add     cx, [bp+di]                                    ;#1B99: 03 0B
        db      0DAh                                           ;#1B9B: DA
        les     di, [bx+1B09h]                                 ;#1B9C: C4 BF 09 1B
        or      al, 0                                          ;#1BA0: 0C 00
        add     [bx+di], ax                                    ;#1BA2: 01 01
        db      0DAh                                           ;#1BA4: DA
        or      di, di                                         ;#1BA5: 0B FF
        add     ax, 0BC4h                                      ;#1BA7: 05 C4 0B
        add     [bx+di], ax                                    ;#1BAA: 01 01
        mov     di, 90Bh                                       ;#1BAC: BF 0B 09
        and     cx, [si]                                       ;#1BAF: 23 0C
        add     [bx+di], al                                    ;#1BB1: 00 01
        add     dx, bx                                         ;#1BB3: 01 DA
        or      di, di                                         ;#1BB5: 0B FF
        add     ax, 0BC4h                                      ;#1BB7: 05 C4 0B
        add     [bx+di], ax                                    ;#1BBA: 01 01
        mov     di, 90Bh                                       ;#1BBC: BF 0B 09
        sub     cx, [si]                                       ;#1BBF: 2B 0C
        add     [bx+di], al                                    ;#1BC1: 00 01
        add     dx, bx                                         ;#1BC3: 01 DA
        or      di, di                                         ;#1BC5: 0B FF
        add     ax, 0BC4h                                      ;#1BC7: 05 C4 0B
        add     [bx+di], ax                                    ;#1BCA: 01 01
        mov     di, 90Bh                                       ;#1BCC: BF 0B 09
        dec     di                                             ;#1BCF: 4F
        push    es                                             ;#1BD0: 06
        add     [bx+di], al                                    ;#1BD1: 00 01
        add     dh, [bp+di+0B303h]                             ;#1BD3: 02 B3 03 B3
        add     cx, [bp+si]                                    ;#1BD7: 03 0A
        db      0Fh                                            ;#1BD9: 0F
        add     al, 0                                          ;#1BDA: 04 00
        add     [bx+di], ax                                    ;#1BDC: 01 01
        mov     bl, 0Bh                                        ;#1BDE: B3 0B
        or      dl, [bx+di]                                    ;#1BE0: 0A 11
        or      [bx+si], al                                    ;#1BE2: 08 00
        inc     word [0BDBh]                                   ;#1BE4: FF 06 DB 0B
        add     [bx+di], ax                                    ;#1BE8: 01 01
        mov     bl, 0Bh                                        ;#1BEA: B3 0B
        or      bl, [bx+di]                                    ;#1BEC: 0A 19
        push    es                                             ;#1BEE: 06
        add     [bx+si], al                                    ;#1BEF: 00 00
        add     cx, [bp+di]                                    ;#1BF1: 03 0B
        db      0DBh                                           ;#1BF3: DB
        db      0DBh                                           ;#1BF4: DB
        mov     bl, 0Ah                                        ;#1BF5: B3 0A
        sbb     ax, 8                                          ;#1BF7: 1D 08 00
        inc     word [0BDBh]                                   ;#1BFA: FF 06 DB 0B
        add     [bx+di], ax                                    ;#1BFE: 01 01
        mov     bl, 0Bh                                        ;#1C00: B3 0B
        or      ah, [di]                                       ;#1C02: 0A 25
        or      [bx+si], al                                    ;#1C04: 08 00
        inc     word [0BDBh]                                   ;#1C06: FF 06 DB 0B
        add     [bx+di], ax                                    ;#1C0A: 01 01
        mov     bl, 0Bh                                        ;#1C0C: B3 0B
        or      ch, [di]                                       ;#1C0E: 0A 2D
        add     al, 0                                          ;#1C10: 04 00
        inc     word [0BDBh]                                   ;#1C12: FF 06 DB 0B
        or      cl, [bx+6]                                     ;#1C16: 0A 4F 06
        add     [bx+di], al                                    ;#1C19: 00 01
        add     dh, [bp+di+0B303h]                             ;#1C1B: 02 B3 03 B3
        add     cx, [bp+di]                                    ;#1C1F: 03 0B
        db      0Fh                                            ;#1C21: 0F
        add     al, 0                                          ;#1C22: 04 00
        add     [bx+di], ax                                    ;#1C24: 01 01
        mov     bl, 0Bh                                        ;#1C26: B3 0B
        or      dx, [bx+di]                                    ;#1C28: 0B 11
        or      [bx+si], al                                    ;#1C2A: 08 00
        add     [di], al                                       ;#1C2C: 00 05
        or      bx, bx                                         ;#1C2E: 0B DB
        db      0DBh                                           ;#1C30: DB
        les     ax, sp                                         ;#1C31: C4 C4
        mov     di, 170Bh                                      ;#1C33: BF 0B 17
        add     al, 0                                          ;#1C36: 04 00
        add     [bx+di], ax                                    ;#1C38: 01 01
        mov     bl, 0Bh                                        ;#1C3A: B3 0B
        or      bx, [bx+di]                                    ;#1C3C: 0B 19
        push    es                                             ;#1C3E: 06
        add     [bx+si], al                                    ;#1C3F: 00 00
        add     cx, [bp+di]                                    ;#1C41: 03 0B
        db      0DBh                                           ;#1C43: DB
        db      0DBh                                           ;#1C44: DB
        mov     bl, 0Bh                                        ;#1C45: B3 0B
        sbb     ax, 8                                          ;#1C47: 1D 08 00
        add     [di], al                                       ;#1C4A: 00 05
        or      bx, bx                                         ;#1C4C: 0B DB
        db      0DBh                                           ;#1C4E: DB
        les     ax, sp                                         ;#1C4F: C4 C4
        mov     di, 230Bh                                      ;#1C51: BF 0B 23
        add     al, 0                                          ;#1C54: 04 00
        add     [bx+di], ax                                    ;#1C56: 01 01
        mov     bl, 0Bh                                        ;#1C58: B3 0B
        or      sp, [di]                                       ;#1C5A: 0B 25
        push    es                                             ;#1C5C: 06
        add     [bx+si], al                                    ;#1C5D: 00 00
        add     cx, [bp+di]                                    ;#1C5F: 03 0B
        db      0DBh                                           ;#1C61: DB
        db      0DBh                                           ;#1C62: DB
        mov     bl, 0Bh                                        ;#1C63: B3 0B
        sub     [0], ax                                        ;#1C65: 29 06 00 00
        add     cx, [bp+di]                                    ;#1C69: 03 0B
        db      0DBh                                           ;#1C6B: DB
        db      0DBh                                           ;#1C6C: DB
        mov     bl, 0Bh                                        ;#1C6D: B3 0B
        sub     ax, 6                                          ;#1C6F: 2D 06 00
        add     [bp+di], al                                    ;#1C72: 00 03
        or      bx, bx                                         ;#1C74: 0B DB
        db      0DBh                                           ;#1C76: DB
        db      0D9h                                           ;#1C77: D9
        or      si, [bx+di]                                    ;#1C78: 0B 31
        push    es                                             ;#1C7A: 06
        add     [bx+di], al                                    ;#1C7B: 00 01
        add     bl, bl                                         ;#1C7D: 02 DB
        or      bx, bx                                         ;#1C7F: 0B DB
        or      cx, [bp+di]                                    ;#1C81: 0B 0B
        dec     di                                             ;#1C83: 4F
        push    es                                             ;#1C84: 06
        add     [bx+di], al                                    ;#1C85: 00 01
        add     dh, [bp+di+0B303h]                             ;#1C87: 02 B3 03 B3
        add     cx, [si]                                       ;#1C8B: 03 0C
        db      0Fh                                            ;#1C8D: 0F
        push    cs                                             ;#1C8E: 0E
        add     [bx+di], al                                    ;#1C8F: 00 01
        add     al, al                                         ;#1C91: 02 C0
        or      ax, sp                                         ;#1C93: 0B C4
        or      di, di                                         ;#1C95: 0B FF
        push    es                                             ;#1C97: 06
        db      0DBh                                           ;#1C98: DB
        or      ax, [bx+di]                                    ;#1C99: 0B 01
        add     [bp+di+0C0Bh], si                              ;#1C9B: 01 B3 0B 0C
        sbb     [bx], cx                                       ;#1C9F: 19 0F
        add     [bx+si], al                                    ;#1CA1: 00 00
        add     al, 0Bh                                        ;#1CA3: 04 0B
        db      0DBh                                           ;#1CA5: DB
        db      0DBh                                           ;#1CA6: DB
        db      0C0h                                           ;#1CA7: C0
        les     di, di                                         ;#1CA8: C4 FF
        push    es                                             ;#1CAA: 06
        db      0DBh                                           ;#1CAB: DB
        or      ax, [bx+di]                                    ;#1CAC: 0B 01
        add     [bp+di+0C0Bh], si                              ;#1CAE: 01 B3 0B 0C
        and     ax, 6                                          ;#1CB2: 25 06 00
        add     [bp+di], al                                    ;#1CB5: 00 03
        or      bx, bx                                         ;#1CB7: 0B DB
        db      0DBh                                           ;#1CB9: DB
        mov     bl, 0Ch                                        ;#1CBA: B3 0C
        sub     [0], ax                                        ;#1CBC: 29 06 00 00
        add     cx, [bp+di]                                    ;#1CC0: 03 0B
        db      0DBh                                           ;#1CC2: DB
        db      0DBh                                           ;#1CC3: DB
        mov     bl, 0Ch                                        ;#1CC4: B3 0C
        sub     ax, 4                                          ;#1CC6: 2D 04 00
        inc     word [0BDBh]                                   ;#1CC9: FF 06 DB 0B
        or      al, 4Fh                                        ;#1CCD: 0C 4F
        push    es                                             ;#1CCF: 06
        add     [bx+di], al                                    ;#1CD0: 00 01
        add     dh, [bp+di+0B303h]                             ;#1CD2: 02 B3 03 B3
        add     cx, [di]                                       ;#1CD6: 03 0D
        db      0Fh                                            ;#1CD8: 0F
        or      al, 0                                          ;#1CD9: 0C 00
        add     [bx+di], ax                                    ;#1CDB: 01 01
        db      0DAh                                           ;#1CDD: DA
        or      di, di                                         ;#1CDE: 0B FF
        add     ax, sp                                         ;#1CE0: 03 C4
        or      ax, [bx+di]                                    ;#1CE2: 0B 01
        add     cx, bx                                         ;#1CE4: 01 D9
        or      cx, [di]                                       ;#1CE6: 0B 0D
        adc     ax, 6                                          ;#1CE8: 15 06 00
        add     [bp+di], al                                    ;#1CEB: 00 03
        or      bx, bx                                         ;#1CED: 0B DB
        db      0DBh                                           ;#1CEF: DB
        mov     bl, 0Dh                                        ;#1CF0: B3 0D
        sbb     [0], cx                                        ;#1CF2: 19 0E 00 00
        add     cx, [bp+di]                                    ;#1CF6: 03 0B
        db      0DBh                                           ;#1CF8: DB
        db      0DBh                                           ;#1CF9: DB
        db      0DAh                                           ;#1CFA: DA
        inc     word [bp+di]                                   ;#1CFB: FF 03
        les     cx, [bp+di]                                    ;#1CFD: C4 0B
        add     [bx+di], ax                                    ;#1CFF: 01 01
        db      0D9h                                           ;#1D01: D9
        or      cx, [di]                                       ;#1D02: 0B 0D
        and     [0], ax                                        ;#1D04: 21 06 00 00
        add     cx, [bp+di]                                    ;#1D08: 03 0B
        db      0DBh                                           ;#1D0A: DB
        db      0DBh                                           ;#1D0B: DB
        mov     bl, 0Dh                                        ;#1D0C: B3 0D
        and     ax, 6                                          ;#1D0E: 25 06 00
        add     [bp+di], al                                    ;#1D11: 00 03
        or      bx, bx                                         ;#1D13: 0B DB
        db      0DBh                                           ;#1D15: DB
        mov     bl, 0Dh                                        ;#1D16: B3 0D
        sub     [0], ax                                        ;#1D18: 29 06 00 00
        add     cx, [bp+di]                                    ;#1D1C: 03 0B
        db      0DBh                                           ;#1D1E: DB
        db      0DBh                                           ;#1D1F: DB
        mov     bl, 0Dh                                        ;#1D20: B3 0D
        sub     ax, 8                                          ;#1D22: 2D 08 00
        add     [di], al                                       ;#1D25: 00 05
        or      bx, bx                                         ;#1D27: 0B DB
        db      0DBh                                           ;#1D29: DB
        les     ax, sp                                         ;#1D2A: C4 C4
        mov     di, 4F0Dh                                      ;#1D2C: BF 0D 4F
        push    es                                             ;#1D2F: 06
        add     [bx+di], al                                    ;#1D30: 00 01
        add     dh, [bp+di+0B303h]                             ;#1D32: 02 B3 03 B3
        add     cx, [MSG_ERRO_SINTATICO_NO_COMANDO_2]          ;#1D36: 03 0E 0F 28
        add     [bx+di], al                                    ;#1D3A: 00 01
        add     al, al                                         ;#1D3C: 02 C0
        or      ax, sp                                         ;#1D3E: 0B C4
        or      di, di                                         ;#1D40: 0B FF
        push    es                                             ;#1D42: 06
        db      0DBh                                           ;#1D43: DB
        or      ax, [bx+si]                                    ;#1D44: 0B 00
        push    es                                             ;#1D46: 06
        or      ax, ax                                         ;#1D47: 0B C0
        les     bx, bx                                         ;#1D49: C4 DB
        db      0DBh                                           ;#1D4B: DB
        db      0C0h                                           ;#1D4C: C0
        les     di, di                                         ;#1D4D: C4 FF
        push    es                                             ;#1D4F: 06
        db      0DBh                                           ;#1D50: DB
        or      ax, [bx+si]                                    ;#1D51: 0B 00
        or      cl, [bp+di]                                    ;#1D53: 0A 0B
        db      0C0h                                           ;#1D55: C0
        les     bx, bx                                         ;#1D56: C4 DB
        db      0DBh                                           ;#1D58: DB
        db      0C0h                                           ;#1D59: C0
        les     bx, bx                                         ;#1D5A: C4 DB
        db      0DBh                                           ;#1D5C: DB
        db      0C0h                                           ;#1D5D: C0
        les     di, di                                         ;#1D5E: C4 FF
        push    es                                             ;#1D60: 06
        db      0DBh                                           ;#1D61: DB
        or      cx, [835h]                                     ;#1D62: 0B 0E 35 08
        add     [bx+si], al                                    ;#1D66: 00 00
        add     ax, 0DA0Bh                                     ;#1D68: 05 0B DA
        les     ax, sp                                         ;#1D6B: C4 C4
        mov     di, 0EC2h                                      ;#1D6D: BF C2 0E
        cmp     ax, 4                                          ;#1D70: 3D 04 00
        add     [bx+di], ax                                    ;#1D73: 01 01
        ret     0E0Bh                                          ;#1D75: C2 0B 0E
        inc     ax                                             ;#1D78: 40
        or      [bx+si], al                                    ;#1D79: 08 00
        add     [di], al                                       ;#1D7B: 00 05
        or      ax, dx                                         ;#1D7D: 0B C2
        db      0DAh                                           ;#1D7F: DA
        les     ax, sp                                         ;#1D80: C4 C4
        mov     di, 4F0Eh                                      ;#1D82: BF 0E 4F
        push    es                                             ;#1D85: 06
        add     [bx+di], al                                    ;#1D86: 00 01
        add     dh, [bp+di+0B303h]                             ;#1D88: 02 B3 03 B3
        add     cx, [bx]                                       ;#1D8C: 03 0F
        xor     ax, 8                                          ;#1D8E: 35 08 00
        add     [di], al                                       ;#1D91: 00 05
        or      ax, bx                                         ;#1D93: 0B C3
        les     ax, sp                                         ;#1D95: C4 C4
        db      0D9h                                           ;#1D97: D9
        mov     bl, 0Fh                                        ;#1D98: B3 0F
        cmp     ax, 4                                          ;#1D9A: 3D 04 00
        add     [bx+di], ax                                    ;#1D9D: 01 01
        mov     bl, 0Bh                                        ;#1D9F: B3 0B
        db      0Fh                                            ;#1DA1: 0F
        inc     ax                                             ;#1DA2: 40
        pop     es                                             ;#1DA3: 07
        add     [bx+si], al                                    ;#1DA4: 00 00
        add     al, 0Bh                                        ;#1DA6: 04 0B
        mov     bl, 0C0h                                       ;#1DA8: B3 C0
        les     ax, sp                                         ;#1DAA: C4 C4
        db      0Fh                                            ;#1DAC: 0F
        inc     sp                                             ;#1DAD: 44
        add     al, 0                                          ;#1DAE: 04 00
        add     [bx+di], ax                                    ;#1DB0: 01 01
        mov     di, 0F0Bh                                      ;#1DB2: BF 0B 0F
        dec     di                                             ;#1DB5: 4F
        push    es                                             ;#1DB6: 06
        add     [bx+di], al                                    ;#1DB7: 00 01
        add     dh, [bp+di+0B303h]                             ;#1DB9: 02 B3 03 B3
        add     dx, [bx+si]                                    ;#1DBD: 03 10
        xor     ax, 6                                          ;#1DBF: 35 06 00
        add     [bp+di], al                                    ;#1DC2: 00 03
        or      ax, cx                                         ;#1DC4: 0B C1
        add     [bx+si], al                                    ;#1DC6: 00 00
        adc     [bx+di], bh                                    ;#1DC8: 10 39
        db      0Fh                                            ;#1DCA: 0F
        add     [bx+si], al                                    ;#1DCB: 00 00
        or      al, 0Bh                                        ;#1DCD: 0C 0B
        db      0C0h                                           ;#1DCF: C0
        les     ax, sp                                         ;#1DD0: C4 C4
        db      0D9h                                           ;#1DD2: D9
        db      0C0h                                           ;#1DD3: C0
        les     ax, sp                                         ;#1DD4: C4 C4
        db      0D9h                                           ;#1DD6: D9
        db      0C0h                                           ;#1DD7: C0
        les     ax, sp                                         ;#1DD8: C4 C4
        db      0D9h                                           ;#1DDA: D9
        adc     [bx+6], cl                                     ;#1DDB: 10 4F 06
        add     [bx+di], al                                    ;#1DDE: 00 01
        add     dh, [bp+di+0B303h]                             ;#1DE0: 02 B3 03 B3
        add     dx, [bx+di]                                    ;#1DE4: 03 11
        dec     di                                             ;#1DE6: 4F
        push    es                                             ;#1DE7: 06
        add     [bx+di], al                                    ;#1DE8: 00 01
        add     dh, [bp+di+0B303h]                             ;#1DEA: 02 B3 03 B3
        add     dx, [bp+si]                                    ;#1DEE: 03 12
        dec     di                                             ;#1DF0: 4F
        push    es                                             ;#1DF1: 06
        add     [bx+di], al                                    ;#1DF2: 00 01
        add     dh, [bp+di+0B303h]                             ;#1DF4: 02 B3 03 B3
        add     dx, [bp+di]                                    ;#1DF8: 03 13
        or      [bp+di], al                                    ;#1DFA: 08 43 00
        add     [bx+si+7], al                                  ;#1DFD: 00 40 07
        dec     di                                             ;#1E00: 4F
        jnb     short MSG_DIREITOS                             ;#1E01: 73 00

MSG_DIREITOS:
        ; "direitos"
        ; Format: FORMAT_STRING
        db      "direitos"                                     ;#1E03: 64 69 72 65 69 74 6F 73
        add     [si+65h], ah                                   ;#1E0B: 00 64 65
        db      0                                              ;#1E0E: 00

MSG_PROPRIEDADE:
        ; "propriedade."
        ; Format: FORMAT_STRING
        db      "propriedade", 0                               ;#1E0F: 70 72 6F 70 72 69 65 64 61 64 65 00

MSG_ESTAO:
        ; "estão."
        ; Format: FORMAT_STRING
        db      "estão", 0                                     ;#1E1B: 65 73 74 84 6F 00

MSG_RESERVADOS:
        ; "reservados"
        ; Format: FORMAT_STRING
        db      "reservados"                                   ;#1E21: 72 65 73 65 72 76 61 64 6F 73
        add     [bx+di], ah                                    ;#1E2B: 00 61 00

MSG_SCOPUS:
        ; "Scopus"
        ; Format: FORMAT_STRING
        db      "Scopus"                                       ;#1E2E: 53 63 6F 70 75 73
        add     [di], ah                                       ;#1E34: 00 65 00

MSG_ITAUTEC:
        ; "Itautec."
        ; Format: FORMAT_STRING
        db      "Itautec."                                     ;#1E37: 49 74 61 75 74 65 63 2E
        add     [bp+di], dl                                    ;#1E3F: 00 13
        dec     di                                             ;#1E41: 4F
        push    es                                             ;#1E42: 06
        add     [bx+di], al                                    ;#1E43: 00 01
        add     dh, [bp+di+0B303h]                             ;#1E45: 02 B3 03 B3
        add     dx, [si]                                       ;#1E49: 03 14
        dec     di                                             ;#1E4B: 4F
        push    dx                                             ;#1E4C: 52
        add     [bx+di], al                                    ;#1E4D: 00 01
        add     dh, [bp+di+0C003h]                             ;#1E4F: 02 B3 03 C0
        add     di, di                                         ;#1E53: 03 FF
        push    es                                             ;#1E55: 06
        add     [bx+si], dh                                    ;#1E56: 00 70 00
        add     al, 70h                                        ;#1E59: 04 70
        cmp     al, [bx+si]                                    ;#1E5B: 3A 00
        add     [bp+si], bh                                    ;#1E5D: 00 3A
        inc     word [di]                                      ;#1E5F: FF 05
        add     [bx+si+1], dh                                  ;#1E61: 00 70 01
        add     [bp+di+0FF70h], si                             ;#1E64: 01 B3 70 FF
        add     ax, [bx+si]                                    ;#1E68: 03 00
        jo      short MSG_PSISNE                               ;#1E6A: 70 00

MSG_PSISNE:
        ; ".pSISNE"
        ; Format: FORMAT_STRING
        db      0Ah, "pSISNE"                                  ;#1E6C: 0A 70 53 49 53 4E 45
        add     [bx+si+4Ch], dl                                ;#1E73: 00 50 4C
        push    bp                                             ;#1E76: 55
        push    bx                                             ;#1E77: 53
        dec     word [7000h]                                   ;#1E78: FF 0E 00 70
        add     [bx+di], ax                                    ;#1E7C: 01 01
        mov     bl, 70h                                        ;#1E7E: B3 70
        inc     word [7000h]                                   ;#1E80: FF 06 00 70
        add     [bx+di], ax                                    ;#1E84: 01 01
        das                                                    ;#1E86: 2F
        jo      short 1E88h                                    ;#1E87: 70 FF
        add     ax, [bx+si]                                    ;#1E89: 03 00
        jo      short 1E8Eh                                    ;#1E8B: 70 01
        add     [bx], bp                                       ;#1E8D: 01 2F
        jo      short 1E90h                                    ;#1E8F: 70 FF
        pop     es                                             ;#1E91: 07
        add     [bx+si+1], dh                                  ;#1E92: 00 70 01
        add     [bp+di+0FF70h], si                             ;#1E95: 01 B3 70 FF
        db      0Fh                                            ;#1E99: 0F
        add     [bx+si+1], dh                                  ;#1E9A: 00 70 01
        add     cx, bx                                         ;#1E9D: 01 D9
        add     ax, [bx+si]                                    ;#1E9F: 03 00
        db      10 dup (0)
        mov     al, [si]                                       ;#1EAB: 8A 04
        inc     si                                             ;#1EAD: 46
        dec     word [615h]                                    ;#1EAE: FF 0E 15 06
        ret                                                    ;#1EB2: C3

MSG_PSQE:
        ; "PSQ.>"
        ; Format: FORMAT_STRING
        db      "PSQ", 8Ah, ">"                                ;#1EB3: 50 53 51 8A 3E
        adc     al, [368Ah]                                    ;#1EB8: 12 06 8A 36
        adc     ax, [168Ah]                                    ;#1EBC: 13 06 8A 16
        adc     al, 6                                          ;#1EC0: 14 06
        mov     ah, 2                                          ;#1EC2: B4 02
        int     10h                                            ;#1EC4: CD 10

MSG_XE:
        ; "Y[X.>"
        ; Format: FORMAT_STRING
        db      "Y[X", 8Ah, ">"                                ;#1EC6: 59 5B 58 8A 3E
        adc     al, [MSG_PARA]                                 ;#1ECB: 12 06 B4 09
        int     10h                                            ;#1ECF: CD 10
        xor     ah, ah                                         ;#1ED1: 32 E4
        mov     al, [614h]                                     ;#1ED3: A0 14 06
        add     ax, cx                                         ;#1ED6: 03 C1
        xor     dh, dh                                         ;#1ED8: 32 F6
        mov     dl, [61Ah]                                     ;#1EDA: 8A 16 1A 06
        cmp     ax, dx                                         ;#1EDE: 3B C2
        jbe     short 1F09h                                    ;#1EE0: 76 27
        sub     dl, [614h]                                     ;#1EE2: 2A 16 14 06
        inc     dl                                             ;#1EE6: FE C2
        sub     cx, dx                                         ;#1EE8: 2B CA
        xor     dh, dh                                         ;#1EEA: 32 F6
        mov     dl, [61Ah]                                     ;#1EEC: 8A 16 1A 06
        inc     dl                                             ;#1EF0: FE C2
        mov     di, dx                                         ;#1EF2: 8B FA
        mov     dl, 1                                          ;#1EF4: B2 01
        cmp     cx, di                                         ;#1EF6: 3B CF
        jb      short 1F00h                                    ;#1EF8: 72 06
        sub     cx, di                                         ;#1EFA: 2B CF
        inc     dl                                             ;#1EFC: FE C2
        jmp     short 1EF6h                                    ;#1EFE: EB F6
        mov     [614h], cl                                     ;#1F00: 88 0E 14 06
        add     [613h], dl                                     ;#1F04: 00 16 13 06
        ret                                                    ;#1F08: C3
        mov     [614h], al                                     ;#1F09: A2 14 06
        ret                                                    ;#1F0C: C3

MSG_PSQRUW:
        ; "PSQRUW"
        ; Format: FORMAT_STRING
        db      "PSQRUW"                                       ;#1F0D: 50 53 51 52 55 57
        push    es                                             ;#1F13: 06
        pushf                                                  ;#1F14: 9C
        mov     byte [611h], 0                                 ;#1F15: C6 06 11 06 00
        mov     ah, 0Fh                                        ;#1F1A: B4 0F
        int     10h                                            ;#1F1C: CD 10
        mov     [612h], bh                                     ;#1F1E: 88 3E 12 06
        dec     ah                                             ;#1F22: FE CC
        mov     [61Ah], ah                                     ;#1F24: 88 26 1A 06
        cmp     al, 7                                          ;#1F28: 3C 07
        jnz     short 1F31h                                    ;#1F2A: 75 05
        mov     byte [611h], 1                                 ;#1F2C: C6 06 11 06 01
        mov     ax, [si]                                       ;#1F31: 8B 04
        add     si, 2                                          ;#1F33: 83 C6 02
        mov     [615h], ax                                     ;#1F36: A3 15 06
        mov     ax, [615h]                                     ;#1F39: A1 15 06
        cmp     ax, 0                                          ;#1F3C: 3D 00 00
        jnz     short 1F44h                                    ;#1F3F: 75 03
        jmp     near 2006h                                     ;#1F41: E9 C2 00
        call    near 1EABh                                     ;#1F44: E8 64 FF
        mov     [613h], al                                     ;#1F47: A2 13 06
        call    near 1EABh                                     ;#1F4A: E8 5E FF
        mov     [614h], al                                     ;#1F4D: A2 14 06
        mov     ax, [si]                                       ;#1F50: 8B 04
        mov     [617h], ax                                     ;#1F52: A3 17 06
        add     si, 2                                          ;#1F55: 83 C6 02
        mov     ax, [615h]                                     ;#1F58: A1 15 06
        sub     ax, 2                                          ;#1F5B: 2D 02 00
        mov     [615h], ax                                     ;#1F5E: A3 15 06
        mov     ax, [617h]                                     ;#1F61: A1 17 06
        cmp     ax, 0                                          ;#1F64: 3D 00 00
        jz      short 1F39h                                    ;#1F67: 74 D0
        call    near 1EABh                                     ;#1F69: E8 3F FF
        mov     cl, al                                         ;#1F6C: 8A C8
        dec     word [617h]                                    ;#1F6E: FF 0E 17 06
        call    near 1EABh                                     ;#1F72: E8 36 FF
        mov     [619h], al                                     ;#1F75: A2 19 06
        dec     word [617h]                                    ;#1F78: FF 0E 17 06
        cmp     cl, 1                                          ;#1F7C: 80 F9 01
        jz      short 1FCEh                                    ;#1F7F: 74 4D
        cmp     cl, 0                                          ;#1F81: 80 F9 00
        jz      short 1FABh                                    ;#1F84: 74 25
        cmp     cl, 0FFh                                       ;#1F86: 80 F9 FF
        jz      short 1F8Eh                                    ;#1F89: 74 03
        jmp     short 1FF3h                                    ;#1F8B: EB 66
        nop                                                    ;#1F8D: 90
        call    near 1EABh                                     ;#1F8E: E8 1A FF
        push    ax                                             ;#1F91: 50
        dec     word [617h]                                    ;#1F92: FF 0E 17 06
        call    near 1EABh                                     ;#1F96: E8 12 FF
        mov     bl, al                                         ;#1F99: 8A D8
        pop     ax                                             ;#1F9B: 58
        dec     word [617h]                                    ;#1F9C: FF 0E 17 06
        xor     cx, cx                                         ;#1FA0: 33 C9
        mov     cl, [619h]                                     ;#1FA2: 8A 0E 19 06
        call    near MSG_PSQE                                  ;#1FA6: E8 0A FF
        jmp     short 1F61h                                    ;#1FA9: EB B6
        call    near 1EABh                                     ;#1FAB: E8 FD FE
        dec     word [617h]                                    ;#1FAE: FF 0E 17 06
        mov     bl, al                                         ;#1FB2: 8A D8
        mov     al, [619h]                                     ;#1FB4: A0 19 06
        cmp     al, 0                                          ;#1FB7: 3C 00
        jz      short 1F61h                                    ;#1FB9: 74 A6
        call    near 1EABh                                     ;#1FBB: E8 ED FE
        dec     word [617h]                                    ;#1FBE: FF 0E 17 06
        dec     byte [619h]                                    ;#1FC2: FE 0E 19 06
        mov     cx, 1                                          ;#1FC6: B9 01 00
        call    near MSG_PSQE                                  ;#1FC9: E8 E7 FE
        jmp     short 1FB4h                                    ;#1FCC: EB E6
        mov     al, [619h]                                     ;#1FCE: A0 19 06
        cmp     al, 0                                          ;#1FD1: 3C 00
        jz      short 1F61h                                    ;#1FD3: 74 8C
        call    near 1EABh                                     ;#1FD5: E8 D3 FE
        push    ax                                             ;#1FD8: 50
        dec     word [617h]                                    ;#1FD9: FF 0E 17 06
        call    near 1EABh                                     ;#1FDD: E8 CB FE
        mov     bl, al                                         ;#1FE0: 8A D8
        pop     ax                                             ;#1FE2: 58
        dec     word [617h]                                    ;#1FE3: FF 0E 17 06
        dec     byte [619h]                                    ;#1FE7: FE 0E 19 06
        mov     cx, 1                                          ;#1FEB: B9 01 00
        call    near MSG_PSQE                                  ;#1FEE: E8 C2 FE
        jmp     short 1FCEh                                    ;#1FF1: EB DB
        mov     bh, [612h]                                     ;#1FF3: 8A 3E 12 06
        mov     al, 7                                          ;#1FF7: B0 07
        mov     ah, 0Eh                                        ;#1FF9: B4 0E
        push    bx                                             ;#1FFB: 53
        push    ax                                             ;#1FFC: 50
        int     10h                                            ;#1FFD: CD 10
        pop     ax                                             ;#1FFF: 58
        pop     bx                                             ;#2000: 5B
        int     10h                                            ;#2001: CD 10
        jmp     short MSG_ZY                                   ;#2003: EB 10
        nop                                                    ;#2005: 90
        cmp     byte [611h], 1                                 ;#2006: 80 3E 11 06 01
        jz      short MSG_ZY                                   ;#200B: 74 08
        mov     bl, [si]                                       ;#200D: 8A 1C
        xor     bh, bh                                         ;#200F: 32 FF
        mov     ah, 0Bh                                        ;#2011: B4 0B
        int     10h                                            ;#2013: CD 10

MSG_ZY:
        ; ".._]ZY[X"
        ; Format: FORMAT_STRING
        db      9Dh, 7, "_]ZY[X"                               ;#2015: 9D 07 5F 5D 5A 59 5B 58
        ret                                                    ;#201D: C3
        db      258 dup (0)
        and     [bx+si], ah                                    ;#2120: 20 20
        scasw                                                  ;#2122: AF
        scasw                                                  ;#2123: AF
        scasw                                                  ;#2124: AF

MSG_COMANDO_INVALIDO:
        ; " Comando inválido....$  "
        ; Format: FORMAT_STRING
        db      " Comando inválido.", 7, 0Dh, 0Ah, "$  "       ;#2125: 20 43 6F 6D 61 6E 64 6F 20 69 6E 76 A0 6C 69 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#213D: AF
        scasw                                                  ;#213E: AF
        scasw                                                  ;#213F: AF

MSG_UNIDADE_INVALIDA_NO_CAMINHO:
        ; " Unidade inválida no caminho....$  "
        ; Format: FORMAT_STRING
        db      " Unidade inválida no caminho.", 7, 0Dh, 0Ah, "$  " ;#2140: 20 55 6E 69 64 61 64 65 20 69 6E 76 A0 6C 69 64 61 20 6E 6F 20 63 61 6D 69 6E 68 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2163: AF
        scasw                                                  ;#2164: AF
        scasw                                                  ;#2165: AF

MSG_UNIDADE_INVALIDA:
        ; " Unidade inválida....$  "
        ; Format: FORMAT_STRING
        db      " Unidade inválida.", 7, 0Dh, 0Ah, "$  "       ;#2166: 20 55 6E 69 64 61 64 65 20 69 6E 76 A0 6C 69 64 61 2E 07 0D 0A 24 20 20
        scasw                                                  ;#217E: AF
        scasw                                                  ;#217F: AF
        scasw                                                  ;#2180: AF

MSG_NUMERO_DE_PARAMETROS_INVALIDO:
        ; " Número de parâmetros inválido..."
        ; Format: FORMAT_STRING
        db      " Número de parâmetros inválido.", 7, 0Dh      ;#2181: 20 4E A3 6D 65 72 6F 20 64 65 20 70 61 72 83 6D 65 74 72 6F 73 20 69 6E 76 A0 6C 69 64 6F 2E 07 0D

MSG_21A2:
        ; ".$  "
        ; Format: FORMAT_STRING
        db      0Ah, "$  "                                     ;#21A2: 0A 24 20 20
        scasw                                                  ;#21A6: AF
        scasw                                                  ;#21A7: AF
        scasw                                                  ;#21A8: AF

MSG_PARAMETRO_INVALIDO:
        ; " Parâmetro inválido....$  "
        ; Format: FORMAT_STRING
        db      " Parâmetro inválido.", 7, 0Dh, 0Ah, "$  "     ;#21A9: 20 50 61 72 83 6D 65 74 72 6F 20 69 6E 76 A0 6C 69 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#21C3: AF
        scasw                                                  ;#21C4: AF
        scasw                                                  ;#21C5: AF

MSG_ARQUIVO_NAO_ENCONTRADO:
        ; " Arquivo não encontrado....$  "
        ; Format: FORMAT_STRING
        db      " Arquivo não encontrado.", 7, 0Dh, 0Ah, "$  " ;#21C6: 20 41 72 71 75 69 76 6F 20 6E 84 6F 20 65 6E 63 6F 6E 74 72 61 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#21E4: AF
        scasw                                                  ;#21E5: AF
        scasw                                                  ;#21E6: AF

MSG_CAMINHO_MUITO_LONGO:
        ; " Caminho muito longo....$"
        ; Format: FORMAT_STRING
        db      " Caminho muito longo.", 7, 0Dh, 0Ah, "$"      ;#21E7: 20 43 61 6D 69 6E 68 6F 20 6D 75 69 74 6F 20 6C 6F 6E 67 6F 2E 07 0D 0A 24

MSG_2200:
        ; " -> ."
        ; Format: FORMAT_STRING
        db      " -> ", 0                                      ;#2200: 20 2D 3E 20 00

MSG_2205:
        ; " ?  (N/S): "
        ; Format: FORMAT_STRING
        db      " ?  (N/S): "                                  ;#2205: 20 3F 20 20 28 4E 2F 53 29 3A 20
        add     [bx+si], ah                                    ;#2210: 00 20
        and     [bx+0AFAFh], ch                                ;#2212: 20 AF AF AF

MSG_JA_EXISTE:
        ; " Já existe $"
        ; Format: FORMAT_STRING
        db      " Já existe $"                                 ;#2216: 20 4A A0 20 65 78 69 73 74 65 20 24

MSG_2222:
        ; "...$  "
        ; Format: FORMAT_STRING
        db      7, 0Dh, 0Ah, "$  "                             ;#2222: 07 0D 0A 24 20 20
        scasw                                                  ;#2228: AF
        scasw                                                  ;#2229: AF
        scasw                                                  ;#222A: AF

MSG_ACESSO_NAO_PERMITIDO:
        ; " Acesso não permitido....$"
        ; Format: FORMAT_STRING
        db      " Acesso não permitido.", 7, 0Dh, 0Ah, "$"     ;#222B: 20 41 63 65 73 73 6F 20 6E 84 6F 20 70 65 72 6D 69 74 69 64 6F 2E 07 0D 0A 24

MSG_TODOS_OS_ARQUIVOS_DEVEM:
        ; "  Todos os arquivos devem ser suprimidos ?"
        ; Format: FORMAT_STRING
        db      "  Todos os arquivos devem ser suprimidos ?  (N/S): $  " ;#2245: 20 20 54 6F 64 6F 73 20 6F 73 20 61 72 71 75 69 76 6F 73 20 64 65 76 65 6D 20 73 65 72 20 73 75 70 72 69 6D 69 64 6F 73 20 3F 20 20 28 4E 2F 53 29 3A 20 24 20 20
        scasw                                                  ;#227B: AF
        scasw                                                  ;#227C: AF
        scasw                                                  ;#227D: AF

MSG_ERRO_SINTATICO_NO_REDIRECIONAMEN:
        ; " Erro sintático no redirecionamento....$  "
        ; Format: FORMAT_STRING
        db      " Erro sintático no redirecionamento.", 7, 0Dh, 0Ah, "$  " ;#227E: 20 45 72 72 6F 20 73 69 6E 74 A0 74 69 63 6F 20 6E 6F 20 72 65 64 69 72 65 63 69 6F 6E 61 6D 65 6E 74 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#22A8: AF
        scasw                                                  ;#22A9: AF
        scasw                                                  ;#22AA: AF

MSG_ERRO_NO_ARQUIVO_DE:
        ; " Erro no arquivo de redirecionamento....$ "
        ; Format: FORMAT_STRING
        db      " Erro no arquivo de redirecionamento.", 7, 0Dh, 0Ah, "$  " ;#22AB: 20 45 72 72 6F 20 6E 6F 20 61 72 71 75 69 76 6F 20 64 65 20 72 65 64 69 72 65 63 69 6F 6E 61 6D 65 6E 74 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#22D6: AF
        scasw                                                  ;#22D7: AF
        scasw                                                  ;#22D8: AF

MSG_ERRO_SINTATICO_NO_ENCADEAMENTO:
        ; " Erro sintático no encadeamento de comando"
        ; Format: FORMAT_STRING
        db      " Erro sintático no encadeamento de comandos.", 7, 0Dh ;#22D9: 20 45 72 72 6F 20 73 69 6E 74 A0 74 69 63 6F 20 6E 6F 20 65 6E 63 61 64 65 61 6D 65 6E 74 6F 20 64 65 20 63 6F 6D 61 6E 64 6F 73 2E 07 0D
        or      ah, [si]                                       ;#2307: 0A 24

MSG_2309:
        ; "..  "
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "  "                                 ;#2309: 0D 0A 20 20
        scasw                                                  ;#230D: AF
        scasw                                                  ;#230E: AF
        scasw                                                  ;#230F: AF

MSG_ERRO_NO_ARQUIVO_TEMPORARIO:
        ; " Erro no arquivo temporário no encadeament"
        ; Format: FORMAT_STRING
        db      " Erro no arquivo temporário no encadeamento de comandos." ;#2310: 20 45 72 72 6F 20 6E 6F 20 61 72 71 75 69 76 6F 20 74 65 6D 70 6F 72 A0 72 69 6F 20 6E 6F 20 65 6E 63 61 64 65 61 6D 65 6E 74 6F 20 64 65 20 63 6F 6D 61 6E 64 6F 73 2E

MSG_2348:
        ; "...$"
        ; Format: FORMAT_STRING
        db      7, 0Dh, 0Ah, "$"                               ;#2348: 07 0D 0A 24

MSG_VOLUME_NA_UNIDADE:
        ; "..   O volume na unidade $"
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "   O volume na unidade $"           ;#234C: 0D 0A 20 20 20 4F 20 76 6F 6C 75 6D 65 20 6E 61 20 75 6E 69 64 61 64 65 20 24

MSG_2366:
        ; " é $"
        ; Format: FORMAT_STRING
        db      " é $"                                         ;#2366: 20 82 20 24

MSG_NAO_TEM_NOME:
        ; " não tem nome..$"
        ; Format: FORMAT_STRING
        db      " não tem nome", 0Dh, 0Ah, "$"                 ;#236A: 20 6E 84 6F 20 74 65 6D 20 6E 6F 6D 65 0D 0A 24

MSG_DIRETORIO_DE:
        ; "   Diretório de $"
        ; Format: FORMAT_STRING
        db      "   Diretório de $"                            ;#237A: 20 20 20 44 69 72 65 74 A2 72 69 6F 20 64 65 20 24

MSG_DIR:
        ; "    <DIR>$"
        ; Format: FORMAT_STRING
        db      "    <DIR>$"                                   ;#238B: 20 20 20 20 3C 44 49 52 3E 24

MSG_2395:
        ; "                 $"
        ; Format: FORMAT_STRING
        db      "                 $"                           ;#2395: 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 20 24

MSG_23A7:
        ; "    $"
        ; Format: FORMAT_STRING
        db      "    $"                                        ;#23A7: 20 20 20 20 24

MSG_ARQUIVO_2:
        ; " Arquivo $"
        ; Format: FORMAT_STRING
        db      " Arquivo $"                                   ;#23AC: 20 41 72 71 75 69 76 6F 20 24

MSG_ARQUIVOS:
        ; " Arquivos$"
        ; Format: FORMAT_STRING
        db      " Arquivos$"                                   ;#23B6: 20 41 72 71 75 69 76 6F 73 24

MSG_DIRETORIO_2:
        ; " Diretório $"
        ; Format: FORMAT_STRING
        db      " Diretório $"                                 ;#23C0: 20 44 69 72 65 74 A2 72 69 6F 20 24

MSG_DIRETORIOS:
        ; " Diretórios$"
        ; Format: FORMAT_STRING
        db      " Diretórios$"                                 ;#23CC: 20 44 69 72 65 74 A2 72 69 6F 73 24

MSG_KBYTES_LIVRES:
        ; " Kbytes livres..$"
        ; Format: FORMAT_STRING
        db      " Kbytes livres", 0Dh, 0Ah, "$"                ;#23D8: 20 4B 62 79 74 65 73 20 6C 69 76 72 65 73 0D 0A 24

MSG_BYTES:
        ; " Bytes$  "
        ; Format: FORMAT_STRING
        db      " Bytes$  "                                    ;#23E9: 20 42 79 74 65 73 24 20 20
        scasw                                                  ;#23F2: AF
        scasw                                                  ;#23F3: AF
        scasw                                                  ;#23F4: AF

MSG_OS_PARAMETROS_ACEITOS_SAO:
        ; " Os parâmetros aceitos são ON e OFF..."
        ; Format: FORMAT_STRING
        db      " Os parâmetros aceitos são ON e OFF.", 7, 0Dh ;#23F5: 20 4F 73 20 70 61 72 83 6D 65 74 72 6F 73 20 61 63 65 69 74 6F 73 20 73 84 6F 20 4F 4E 20 65 20 4F 46 46 2E 07 0D

MSG_241B:
        ; ".$  "
        ; Format: FORMAT_STRING
        db      0Ah, "$  "                                     ;#241B: 0A 24 20 20
        scasw                                                  ;#241F: AF
        scasw                                                  ;#2420: AF
        scasw                                                  ;#2421: AF

MSG_DISPOSITIVO_BRASCII_NAO_INSTALAD:
        ; " Dispositivo BRASCII não instalado....$  "
        ; Format: FORMAT_STRING
        db      " Dispositivo BRASCII não instalado.", 7, 0Dh, 0Ah, "$  " ;#2422: 20 44 69 73 70 6F 73 69 74 69 76 6F 20 42 52 41 53 43 49 49 20 6E 84 6F 20 69 6E 73 74 61 6C 61 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#244B: AF
        scasw                                                  ;#244C: AF
        scasw                                                  ;#244D: AF

MSG_BRASCII_NAO_SUPORTADO:
        ; " BRASCII não suportado....$"
        ; Format: FORMAT_STRING
        db      " BRASCII não suportado.", 7, 0Dh, 0Ah, "$"    ;#244E: 20 42 52 41 53 43 49 49 20 6E 84 6F 20 73 75 70 6F 72 74 61 64 6F 2E 07 0D 0A 24

MSG_BREAK:
        ; "  BREAK$"
        ; Format: FORMAT_STRING
        db      "  BREAK$"                                     ;#2469: 20 20 42 52 45 41 4B 24

MSG_VERIFY:
        ; "  VERIFY$"
        ; Format: FORMAT_STRING
        db      "  VERIFY$"                                    ;#2471: 20 20 56 45 52 49 46 59 24

MSG_ECHO:
        ; "  ECHO$"
        ; Format: FORMAT_STRING
        db      "  ECHO$"                                      ;#247A: 20 20 45 43 48 4F 24

MSG_BRASCII:
        ; "  BRASCII$"
        ; Format: FORMAT_STRING
        db      "  BRASCII$"                                   ;#2481: 20 20 42 52 41 53 43 49 49 24

MSG_OPTIONS:
        ; "  OPTIONS$"
        ; Format: FORMAT_STRING
        db      "  OPTIONS$"                                   ;#248B: 20 20 4F 50 54 49 4F 4E 53 24

MSG_FILTRO_DA_IMPRESSORA:
        ; "  FILTRO da impressora$"
        ; Format: FORMAT_STRING
        db      "  FILTRO da impressora$"                      ;#2495: 20 20 46 49 4C 54 52 4F 20 64 61 20 69 6D 70 72 65 73 73 6F 72 61 24

MSG_ESTA_INATIVO_OFF:
        ; " está inativo (OFF)...$"
        ; Format: FORMAT_STRING
        db      " está inativo (OFF).", 0Dh, 0Ah, "$"          ;#24AC: 20 65 73 74 A0 20 69 6E 61 74 69 76 6F 20 28 4F 46 46 29 2E 0D 0A 24

MSG_ESTA_ATIVO_ON:
        ; " está ativo (ON)...$  "
        ; Format: FORMAT_STRING
        db      " está ativo (ON).", 0Dh, 0Ah, "$  "           ;#24C3: 20 65 73 74 A0 20 61 74 69 76 6F 20 28 4F 4E 29 2E 0D 0A 24 20 20
        scasw                                                  ;#24D9: AF
        scasw                                                  ;#24DA: AF
        scasw                                                  ;#24DB: AF

MSG_ERRO_SINTATICO_NO_COMANDO:
        ; " Erro sintático no comando....$  "
        ; Format: FORMAT_STRING
        db      " Erro sintático no comando.", 7, 0Dh, 0Ah, "$  " ;#24DC: 20 45 72 72 6F 20 73 69 6E 74 A0 74 69 63 6F 20 6E 6F 20 63 6F 6D 61 6E 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#24FD: AF
        scasw                                                  ;#24FE: AF
        scasw                                                  ;#24FF: AF

MSG_EXCEDEU_AREA_DE_CONTEXTO:
        ; " Excedeu a área de contexto....$"
        ; Format: FORMAT_STRING
        db      " Excedeu a área de contexto.", 7, 0Dh, 0Ah, "$" ;#2500: 20 45 78 63 65 64 65 75 20 61 20 A0 72 65 61 20 64 65 20 63 6F 6E 74 65 78 74 6F 2E 07 0D 0A 24

MSG_NAO_HA_CAMINHO_DEFINIDO:
        ; "  Não há caminho definido...$"
        ; Format: FORMAT_STRING
        db      "  Não há caminho definido.", 0Dh, 0Ah, "$"    ;#2520: 20 20 4E 84 6F 20 68 A0 20 63 61 6D 69 6E 68 6F 20 64 65 66 69 6E 69 64 6F 2E 0D 0A 24

MSG_PATH_PROMPT:
        ; "PATH=PROMPT="
        ; Format: FORMAT_STRING
        db      "PATH=PROMPT="                                 ;#253D: 50 41 54 48 3D 50 52 4F 4D 50 54 3D
        adc     [bx+si], cl                                    ;#2549: 10 08
        and     [bx+si], cl                                    ;#254B: 20 08

MSG_254D:
        ; "$..$  $"
        ; Format: FORMAT_STRING
        db      "$", 0Dh, 0Ah, "$  $"                          ;#254D: 24 0D 0A 24 20 20 24

MSG_2554:
        ; "04261537"
        ; Format: FORMAT_STRING
        db      "04261537"                                     ;#2554: 30 34 32 36 31 35 33 37
        sbb     bx, [bp+di+32h]                                ;#255C: 1B 5B 32
        dec     dx                                             ;#255F: 4A
        and     al, 1Bh                                        ;#2560: 24 1B

MSG_2562:
        ; "[3$;4$m$"
        ; Format: FORMAT_STRING
        db      "[3$;4$m$"                                     ;#2562: 5B 33 24 3B 34 24 6D 24
        sbb     bx, [bp+di+30h]                                ;#256A: 1B 5B 30
        db      6Dh                                            ;#256D: 6D
        and     al, 1Bh                                        ;#256E: 24 1B
        pop     bx                                             ;#2570: 5B
        xor     [di+24h], bp                                   ;#2571: 31 6D 24
        db      1Bh                                            ;#2574: 1B

MSG_2575:
        ; "[5m$  "
        ; Format: FORMAT_STRING
        db      "[5m$  "                                       ;#2575: 5B 35 6D 24 20 20
        scasw                                                  ;#257B: AF
        scasw                                                  ;#257C: AF
        scasw                                                  ;#257D: AF

MSG_DIRETORIO_INVALIDO:
        ; " Diretório inválido....$  "
        ; Format: FORMAT_STRING
        db      " Diretório inválido.", 7, 0Dh, 0Ah, "$  "     ;#257E: 20 44 69 72 65 74 A2 72 69 6F 20 69 6E 76 A0 6C 69 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2598: AF
        scasw                                                  ;#2599: AF
        scasw                                                  ;#259A: AF

MSG_DIRETORIO_INVALIDO_OU_NAO:
        ; " Diretório inválido ou não vazio.."
        ; Format: FORMAT_STRING
        db      " Diretório inválido ou não vazio.", 7         ;#259B: 20 44 69 72 65 74 A2 72 69 6F 20 69 6E 76 A0 6C 69 64 6F 20 6F 75 20 6E 84 6F 20 76 61 7A 69 6F 2E 07

MSG_25BD:
        ; "..$  "
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "$  "                                ;#25BD: 0D 0A 24 20 20
        scasw                                                  ;#25C2: AF
        scasw                                                  ;#25C3: AF
        scasw                                                  ;#25C4: AF

MSG_IMPOSSIVEL_CRIAR_DIRETORIO:
        ; " Impossível criar o diretório...."
        ; Format: FORMAT_STRING
        db      " Impossível criar o diretório.", 7, 0Dh, 0Ah  ;#25C5: 20 49 6D 70 6F 73 73 A1 76 65 6C 20 63 72 69 61 72 20 6F 20 64 69 72 65 74 A2 72 69 6F 2E 07 0D 0A
        db      24h                                            ;#25E6: 24

MSG_DIGITE_UMA_TECLA_PARA_2:
        ; "  Digite uma tecla para continuar $  "
        ; Format: FORMAT_STRING
        db      "  Digite uma tecla para continuar $  "        ;#25E7: 20 20 44 69 67 69 74 65 20 75 6D 61 20 74 65 63 6C 61 20 70 61 72 61 20 63 6F 6E 74 69 6E 75 61 72 20 24 20 20
        scasw                                                  ;#260C: AF
        scasw                                                  ;#260D: AF
        scasw                                                  ;#260E: AF

MSG_DISPOSITIVO_INVALIDO:
        ; " Dispositivo inválido....$  "
        ; Format: FORMAT_STRING
        db      " Dispositivo inválido.", 7, 0Dh, 0Ah, "$  "   ;#260F: 20 44 69 73 70 6F 73 69 74 69 76 6F 20 69 6E 76 A0 6C 69 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#262B: AF
        scasw                                                  ;#262C: AF
        scasw                                                  ;#262D: AF

MSG_DATA_INVALIDA:
        ; " Data inválida....$  "
        ; Format: FORMAT_STRING
        db      " Data inválida.", 7, 0Dh, 0Ah, "$  "          ;#262E: 20 44 61 74 61 20 69 6E 76 A0 6C 69 64 61 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2643: AF
        scasw                                                  ;#2644: AF
        scasw                                                  ;#2645: AF

MSG_HORA_INVALIDA:
        ; " Hora inválida....$"
        ; Format: FORMAT_STRING
        db      " Hora inválida.", 7, 0Dh, 0Ah, "$"            ;#2646: 20 48 6F 72 61 20 69 6E 76 A0 6C 69 64 61 2E 07 0D 0A 24

MSG_ATUALIZE:
        ; "..  Atualize: $"
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "  Atualize: $"                      ;#2659: 0D 0A 20 20 41 74 75 61 6C 69 7A 65 3A 20 24

MSG_JANFEVMARABRMAIJUNJULAGOSETOUTNO:
        ; "JanFevMarAbrMaiJunJulAgoSetOutNovDezDomSeg"
        ; Format: FORMAT_STRING
        db      "JanFevMarAbrMaiJunJulAgoSetOutNovDezDomSegTerQuaQuiSexSab  " ;#2668: 4A 61 6E 46 65 76 4D 61 72 41 62 72 4D 61 69 4A 75 6E 4A 75 6C 41 67 6F 53 65 74 4F 75 74 4E 6F 76 44 65 7A 44 6F 6D 53 65 67 54 65 72 51 75 61 51 75 69 53 65 78 53 61 62 20 20
        scasw                                                  ;#26A3: AF
        scasw                                                  ;#26A4: AF
        scasw                                                  ;#26A5: AF

MSG_UNIDADE_INCONSISTENTE:
        ; " Unidade inconsistente....$  "
        ; Format: FORMAT_STRING
        db      " Unidade inconsistente.", 7, 0Dh, 0Ah, "$  "  ;#26A6: 20 55 6E 69 64 61 64 65 20 69 6E 63 6F 6E 73 69 73 74 65 6E 74 65 2E 07 0D 0A 24 20 20
        scasw                                                  ;#26C3: AF
        scasw                                                  ;#26C4: AF
        scasw                                                  ;#26C5: AF

MSG_CAMINHO_INVALIDO:
        ; " Caminho inválido....$  "
        ; Format: FORMAT_STRING
        db      " Caminho inválido.", 7, 0Dh, 0Ah, "$  "       ;#26C6: 20 43 61 6D 69 6E 68 6F 20 69 6E 76 A0 6C 69 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#26DE: AF
        scasw                                                  ;#26DF: AF
        scasw                                                  ;#26E0: AF

MSG_NAO_EXISTE_ASSOCIACAO_NESSA:
        ; " Não existe associação nessa unidade.."
        ; Format: FORMAT_STRING
        db      " Não existe associação nessa unidade.", 7     ;#26E1: 20 4E 84 6F 20 65 78 69 73 74 65 20 61 73 73 6F 63 69 61 87 84 6F 20 6E 65 73 73 61 20 75 6E 69 64 61 64 65 2E 07

MSG_2707:
        ; "..$  "
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "$  "                                ;#2707: 0D 0A 24 20 20
        scasw                                                  ;#270C: AF
        scasw                                                  ;#270D: AF
        scasw                                                  ;#270E: AF

MSG_IMPOSSIVEL_ASSOCIAR_UNIDADE:
        ; " Impossível associar a unidade....$"
        ; Format: FORMAT_STRING
        db      " Impossível associar a unidade.", 7, 0Dh, 0Ah, "$" ;#270F: 20 49 6D 70 6F 73 73 A1 76 65 6C 20 61 73 73 6F 63 69 61 72 20 61 20 75 6E 69 64 61 64 65 2E 07 0D 0A 24

MSG_APPEND:
        ; "APPEND=  "
        ; Format: FORMAT_STRING
        db      "APPEND=  "                                    ;#2732: 41 50 50 45 4E 44 3D 20 20
        scasw                                                  ;#273B: AF
        scasw                                                  ;#273C: AF
        scasw                                                  ;#273D: AF

MSG_CONFLITO_DE_VERSAO:
        ; " Conflito de versão....$"
        ; Format: FORMAT_STRING
        db      " Conflito de versão.", 7, 0Dh, 0Ah, "$"       ;#273E: 20 43 6F 6E 66 6C 69 74 6F 20 64 65 20 76 65 72 73 84 6F 2E 07 0D 0A 24

MSG_APPEND_2:
        ; "  APPEND$"
        ; Format: FORMAT_STRING
        db      "  APPEND$"                                    ;#2756: 20 20 41 50 50 45 4E 44 24

MSG_275F:
        ; "    /X  $"
        ; Format: FORMAT_STRING
        db      "    /X  $"                                    ;#275F: 20 20 20 20 2F 58 20 20 24

MSG_2768:
        ; "    /E  $"
        ; Format: FORMAT_STRING
        db      "    /E  $"                                    ;#2768: 20 20 20 20 2F 45 20 20 24

MSG_ESTA_ATIVO:
        ; " está ativo...$"
        ; Format: FORMAT_STRING
        db      " está ativo.", 0Dh, 0Ah, "$"                  ;#2771: 20 65 73 74 A0 20 61 74 69 76 6F 2E 0D 0A 24

MSG_ESTA_INATIVO:
        ; " está inativo...$  "
        ; Format: FORMAT_STRING
        db      " está inativo.", 0Dh, 0Ah, "$  "              ;#2780: 20 65 73 74 A0 20 69 6E 61 74 69 76 6F 2E 0D 0A 24 20 20
        scasw                                                  ;#2793: AF
        scasw                                                  ;#2794: AF
        scasw                                                  ;#2795: AF

MSG_COMANDO_NAO_IMPLEMENTADO:
        ; " Comando não implementado....$  "
        ; Format: FORMAT_STRING
        db      " Comando não implementado.", 7, 0Dh, 0Ah, "$  " ;#2796: 20 43 6F 6D 61 6E 64 6F 20 6E 84 6F 20 69 6D 70 6C 65 6D 65 6E 74 61 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#27B6: AF
        scasw                                                  ;#27B7: AF
        scasw                                                  ;#27B8: AF

MSG_MEMORIA_INSUFICIENTE_PARA_COMAND:
        ; " Memória insuficiente para comando CALL..."
        ; Format: FORMAT_STRING
        db      " Memória insuficiente para comando CALL.", 7, 0Dh, 0Ah ;#27B9: 20 4D 65 6D A2 72 69 61 20 69 6E 73 75 66 69 63 69 65 6E 74 65 20 70 61 72 61 20 63 6F 6D 61 6E 64 6F 20 43 41 4C 4C 2E 07 0D 0A
        db      24h                                            ;#27E4: 24

MSG_27E5:
        ; "..  "
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "  "                                 ;#27E5: 0D 0A 20 20
        scasw                                                  ;#27E9: AF
        scasw                                                  ;#27EA: AF
        scasw                                                  ;#27EB: AF

MSG_LINHA_DO_FOR_MUITO:
        ; " Linha do FOR muito longa....$  "
        ; Format: FORMAT_STRING
        db      " Linha do FOR muito longa.", 7, 0Dh, 0Ah, "$  " ;#27EC: 20 4C 69 6E 68 61 20 64 6F 20 46 4F 52 20 6D 75 69 74 6F 20 6C 6F 6E 67 61 2E 07 0D 0A 24 20 20
        scasw                                                  ;#280C: AF
        scasw                                                  ;#280D: AF
        scasw                                                  ;#280E: AF

MSG_ERRO_SINTATICO_NO_COMANDO_2:
        ; " Erro sintático no comando FOR....$  "
        ; Format: FORMAT_STRING
        db      " Erro sintático no comando FOR.", 7, 0Dh, 0Ah, "$  " ;#280F: 20 45 72 72 6F 20 73 69 6E 74 A0 74 69 63 6F 20 6E 6F 20 63 6F 6D 61 6E 64 6F 20 46 4F 52 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2834: AF
        scasw                                                  ;#2835: AF
        scasw                                                  ;#2836: AF

MSG_FOR_NAO_PODE_SER:
        ; " FOR não pode ser encadeado....$  "
        ; Format: FORMAT_STRING
        db      " FOR não pode ser encadeado.", 7, 0Dh, 0Ah, "$  " ;#2837: 20 46 4F 52 20 6E 84 6F 20 70 6F 64 65 20 73 65 72 20 65 6E 63 61 64 65 61 64 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2859: AF
        scasw                                                  ;#285A: AF
        scasw                                                  ;#285B: AF

MSG_ERRO_SINTATICO_NO_COMANDO_3:
        ; " Erro sintático no comando IF....$  "
        ; Format: FORMAT_STRING
        db      " Erro sintático no comando IF.", 7, 0Dh, 0Ah, "$  " ;#285C: 20 45 72 72 6F 20 73 69 6E 74 A0 74 69 63 6F 20 6E 6F 20 63 6F 6D 61 6E 64 6F 20 49 46 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2880: AF
        scasw                                                  ;#2881: AF
        scasw                                                  ;#2882: AF

MSG_ERRO_SINTATICO_NO_COMANDO_4:
        ; " Erro sintático no comando GOTO....$  "
        ; Format: FORMAT_STRING
        db      " Erro sintático no comando GOTO.", 7, 0Dh, 0Ah, "$  " ;#2883: 20 45 72 72 6F 20 73 69 6E 74 A0 74 69 63 6F 20 6E 6F 20 63 6F 6D 61 6E 64 6F 20 47 4F 54 4F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#28A9: AF
        scasw                                                  ;#28AA: AF
        scasw                                                  ;#28AB: AF

MSG_ROTULO_NAO_ENCONTRADO:
        ; " Rótulo não encontrado....$"
        ; Format: FORMAT_STRING
        db      " Rótulo não encontrado.", 7, 0Dh, 0Ah, "$"    ;#28AC: 20 52 A2 74 75 6C 6F 20 6E 84 6F 20 65 6E 63 6F 6E 74 72 61 64 6F 2E 07 0D 0A 24

MSG_28C7:
        ; "..  "
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "  "                                 ;#28C7: 0D 0A 20 20
        scasw                                                  ;#28CB: AF
        scasw                                                  ;#28CC: AF
        scasw                                                  ;#28CD: AF

MSG_LINHA_DO_ARQUIVO_DE:
        ; " Linha do arquivo de comandos muito longa."
        ; Format: FORMAT_STRING
        db      " Linha do arquivo de comandos muito longa.", 7, 0Dh, 0Ah, "$" ;#28CE: 20 4C 69 6E 68 61 20 64 6F 20 61 72 71 75 69 76 6F 20 64 65 20 63 6F 6D 61 6E 64 6F 73 20 6D 75 69 74 6F 20 6C 6F 6E 67 61 2E 07 0D 0A 24

MSG_28FC:
        ; "..  "
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "  "                                 ;#28FC: 0D 0A 20 20
        scasw                                                  ;#2900: AF
        scasw                                                  ;#2901: AF
        scasw                                                  ;#2902: AF

MSG_ARQUIVO_DE_COMANDOS_DEFEITUOSO:
        ; " Arquivo de comandos defeituoso ou ausente"
        ; Format: FORMAT_STRING
        db      " Arquivo de comandos defeituoso ou ausente.", 7, 0Dh, 0Ah, "$" ;#2903: 20 41 72 71 75 69 76 6F 20 64 65 20 63 6F 6D 61 6E 64 6F 73 20 64 65 66 65 69 74 75 6F 73 6F 20 6F 75 20 61 75 73 65 6E 74 65 2E 07 0D 0A 24

MSG_PROCESSAMENTO_DO_ARQUIVO_DE:
        ; "      Processamento do arquivo de comandos"
        ; Format: FORMAT_STRING
        db      "      Processamento do arquivo de comandos cancelado.", 0Dh, 0Ah, "$" ;#2932: 20 20 20 20 20 20 50 72 6F 63 65 73 73 61 6D 65 6E 74 6F 20 64 6F 20 61 72 71 75 69 76 6F 20 64 65 20 63 6F 6D 61 6E 64 6F 73 20 63 61 6E 63 65 6C 61 64 6F 2E 0D 0A 24

MSG_COLOQUE_DISCO_COM_ARQUIVO:
        ; "      Coloque o disco com o arquivo de com"
        ; Format: FORMAT_STRING
        db      "      Coloque o disco com o arquivo de comandos.", 0Dh, 0Ah, "    $" ;#296A: 20 20 20 20 20 20 43 6F 6C 6F 71 75 65 20 6F 20 64 69 73 63 6F 20 63 6F 6D 20 6F 20 61 72 71 75 69 76 6F 20 64 65 20 63 6F 6D 61 6E 64 6F 73 2E 0D 0A 20 20 20 20 24

MSG_29A1:
        ; "..  "
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "  "                                 ;#29A1: 0D 0A 20 20
        scasw                                                  ;#29A5: AF
        scasw                                                  ;#29A6: AF
        scasw                                                  ;#29A7: AF

MSG_COMANDO_FOR_OU_ENCADEAMENTO:
        ; " Comando FOR ou encadeamento de comandos d"
        ; Format: FORMAT_STRING
        db      " Comando FOR ou encadeamento de comandos desativado", 0Dh, 0Ah, "   " ;#29A8: 20 43 6F 6D 61 6E 64 6F 20 46 4F 52 20 6F 75 20 65 6E 63 61 64 65 61 6D 65 6E 74 6F 20 64 65 20 63 6F 6D 61 6E 64 6F 73 20 64 65 73 61 74 69 76 61 64 6F 0D 0A 20 20 20

MSG_PARA_EXECUTAR_ARQUIVO_DE:
        ; "   para executar arquivo de comandos....$ "
        ; Format: FORMAT_STRING
        db      "   para executar arquivo de comandos.", 7, 0Dh, 0Ah, "$  " ;#29E0: 20 20 20 70 61 72 61 20 65 78 65 63 75 74 61 72 20 61 72 71 75 69 76 6F 20 64 65 20 63 6F 6D 61 6E 64 6F 73 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2A0B: AF
        scasw                                                  ;#2A0C: AF
        scasw                                                  ;#2A0D: AF

MSG_CAMINHO_INVALIDO_OU_ARQUIVO:
        ; " Caminho inválido ou arquivo não encontrad"
        ; Format: FORMAT_STRING
        db      " Caminho inválido ou arquivo não encontrado.", 7 ;#2A0E: 20 43 61 6D 69 6E 68 6F 20 69 6E 76 A0 6C 69 64 6F 20 6F 75 20 61 72 71 75 69 76 6F 20 6E 84 6F 20 65 6E 63 6F 6E 74 72 61 64 6F 2E 07

MSG_2A3B:
        ; "..$  "
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "$  "                                ;#2A3B: 0D 0A 24 20 20
        scasw                                                  ;#2A40: AF
        scasw                                                  ;#2A41: AF
        scasw                                                  ;#2A42: AF

MSG_ERRO_NA_CRIACAO_DO:
        ; " Erro na criação do arquivo....$  "
        ; Format: FORMAT_STRING
        db      " Erro na criação do arquivo.", 7, 0Dh, 0Ah, "$  " ;#2A43: 20 45 72 72 6F 20 6E 61 20 63 72 69 61 87 84 6F 20 64 6F 20 61 72 71 75 69 76 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2A65: AF
        scasw                                                  ;#2A66: AF
        scasw                                                  ;#2A67: AF

MSG_ERRO_NA_LEITURA_DO:
        ; " Erro na leitura do arquivo....$  "
        ; Format: FORMAT_STRING
        db      " Erro na leitura do arquivo.", 7, 0Dh, 0Ah, "$  " ;#2A68: 20 45 72 72 6F 20 6E 61 20 6C 65 69 74 75 72 61 20 64 6F 20 61 72 71 75 69 76 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2A8A: AF
        scasw                                                  ;#2A8B: AF
        scasw                                                  ;#2A8C: AF

MSG_ERRO_NA_ESCRITA_DO:
        ; " Erro na escrita do arquivo....$  "
        ; Format: FORMAT_STRING
        db      " Erro na escrita do arquivo.", 7, 0Dh, 0Ah, "$  " ;#2A8D: 20 45 72 72 6F 20 6E 61 20 65 73 63 72 69 74 61 20 64 6F 20 61 72 71 75 69 76 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2AAF: AF
        scasw                                                  ;#2AB0: AF
        scasw                                                  ;#2AB1: AF

MSG_DISCO_CHEIO:
        ; " Disco cheio....$  "
        ; Format: FORMAT_STRING
        db      " Disco cheio.", 7, 0Dh, 0Ah, "$  "            ;#2AB2: 20 44 69 73 63 6F 20 63 68 65 69 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2AC5: AF
        scasw                                                  ;#2AC6: AF
        scasw                                                  ;#2AC7: AF

MSG_ERRO_DE_ESCRITA_NO:
        ; " Erro de escrita no dispositivo....$  "
        ; Format: FORMAT_STRING
        db      " Erro de escrita no dispositivo.", 7, 0Dh, 0Ah, "$  " ;#2AC8: 20 45 72 72 6F 20 64 65 20 65 73 63 72 69 74 61 20 6E 6F 20 64 69 73 70 6F 73 69 74 69 76 6F 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2AEE: AF
        scasw                                                  ;#2AEF: AF
        scasw                                                  ;#2AF0: AF

MSG_IMPOSSIVEL_MUDAR_DATA_DE:
        ; " Impossível mudar a data de dispositivos.."
        ; Format: FORMAT_STRING
        db      " Impossível mudar a data de dispositivos.", 7, 0Dh, 0Ah ;#2AF1: 20 49 6D 70 6F 73 73 A1 76 65 6C 20 6D 75 64 61 72 20 61 20 64 61 74 61 20 64 65 20 64 69 73 70 6F 73 69 74 69 76 6F 73 2E 07 0D 0A

MSG_2B1D:
        ; "$  "
        ; Format: FORMAT_STRING
        db      "$  "                                          ;#2B1D: 24 20 20
        scasw                                                  ;#2B20: AF
        scasw                                                  ;#2B21: AF
        scasw                                                  ;#2B22: AF

MSG_NAO_POSSIVEL_EFETUAR_LEITURA:
        ; " Não é possível efetuar leitura biná"
        ; Format: FORMAT_STRING
        db      " Não é possível efetuar leitura biná"         ;#2B23: 20 4E 84 6F 20 82 20 70 6F 73 73 A1 76 65 6C 20 65 66 65 74 75 61 72 20 6C 65 69 74 75 72 61 20 62 69 6E A0

MSG_RIA_DE_DISPOSITIVOS:
        ; "ria de dispositivos....$  "
        ; Format: FORMAT_STRING
        db      "ria de dispositivos.", 7, 0Dh, 0Ah, "$  "     ;#2B47: 72 69 61 20 64 65 20 64 69 73 70 6F 73 69 74 69 76 6F 73 2E 07 0D 0A 24 20 20
        scasw                                                  ;#2B61: AF
        scasw                                                  ;#2B62: AF
        scasw                                                  ;#2B63: AF

MSG_CONTEUDO_DO_DESTINO_PERDIDO:
        ; " Conteúdo do destino perdido antes da cópi"
        ; Format: FORMAT_STRING
        db      " Conteúdo do destino perdido antes da cópia.", 7 ;#2B64: 20 43 6F 6E 74 65 A3 64 6F 20 64 6F 20 64 65 73 74 69 6E 6F 20 70 65 72 64 69 64 6F 20 61 6E 74 65 73 20 64 61 20 63 A2 70 69 61 2E 07

MSG_2B91:
        ; "..$  "
        ; Format: FORMAT_STRING
        db      0Dh, 0Ah, "$  "                                ;#2B91: 0D 0A 24 20 20
        scasw                                                  ;#2B96: AF
        scasw                                                  ;#2B97: AF
        scasw                                                  ;#2B98: AF

MSG_NAO_COPIA_SOBRE_ELE:
        ; " Não copia sobre ele mesmo....$"
        ; Format: FORMAT_STRING
        db      " Não copia sobre ele mesmo.", 7, 0Dh, 0Ah, "$" ;#2B99: 20 4E 84 6F 20 63 6F 70 69 61 20 73 6F 62 72 65 20 65 6C 65 20 6D 65 73 6D 6F 2E 07 0D 0A 24

MSG_DESEJA_GERAR:
        ; "  Deseja gerar $"
        ; Format: FORMAT_STRING
        db      "  Deseja gerar $"                             ;#2BB8: 20 20 44 65 73 65 6A 61 20 67 65 72 61 72 20 24

MSG_JA_EXISTE_ARQUIVO_DESTINO:
        ; "  Já existe o arquivo destino $"
        ; Format: FORMAT_STRING
        db      "  Já existe o arquivo destino $"              ;#2BC8: 20 20 4A A0 20 65 78 69 73 74 65 20 6F 20 61 72 71 75 69 76 6F 20 64 65 73 74 69 6E 6F 20 24

MSG_DESTRUIR:
        ; " , destruir ?  (N/S): $"
        ; Format: FORMAT_STRING
        db      " , destruir ?  (N/S): $"                      ;#2BE7: 20 2C 20 64 65 73 74 72 75 69 72 20 3F 20 20 28 4E 2F 53 29 3A 20 24

MSG_ARQUIVO_COPIADO:
        ; " arquivo(s) copiado(s)...$"
        ; Format: FORMAT_STRING
        db      " arquivo(s) copiado(s).", 0Dh, 0Ah, "$"       ;#2BFE: 20 61 72 71 75 69 76 6F 28 73 29 20 63 6F 70 69 61 64 6F 28 73 29 2E 0D 0A 24
        add     [bx-4Ah], bx                                   ;#2C18: 01 5F B6
        sbb     al, [bx+di]                                    ;#2C1B: 1A 01
        dec     si                                             ;#2C1D: 4E
        ret                                                    ;#2C1E: C3
        sbb     al, [bx+di]                                    ;#2C1F: 1A 01
        and     al, 0FFh                                       ;#2C21: 24 FF
        sbb     al, [bx+di]                                    ;#2C23: 1A 01
        inc     bp                                             ;#2C25: 45
        add     bx, [bp+di]                                    ;#2C26: 03 1B
        add     [si+7], cx                                     ;#2C28: 01 4C 07
        sbb     ax, [bx+di]                                    ;#2C2B: 1B 01
        push    cx                                             ;#2C2D: 51
        or      bx, [bp+di]                                    ;#2C2E: 0B 1B
        add     [bx+0Fh], ax                                   ;#2C30: 01 47 0F
        sbb     ax, [bx+di]                                    ;#2C33: 1B 01
        inc     dx                                             ;#2C35: 42
        adc     bx, [bp+di]                                    ;#2C36: 13 1B
        add     [bx+si+17h], cx                                ;#2C38: 01 48 17
        sbb     ax, [bx+di]                                    ;#2C3B: 1B 01
        push    ax                                             ;#2C3D: 50
        sbb     ax, 11Bh                                       ;#2C3E: 1D 1B 01
        push    si                                             ;#2C41: 56
        xor     bl, [bp+di]                                    ;#2C42: 32 1B
        add     [si+3Ch], ax                                   ;#2C44: 01 44 3C
        sbb     ax, [bx+di]                                    ;#2C47: 1B 01
        push    sp                                             ;#2C49: 54
        jnp     short 2C67h                                    ;#2C4A: 7B 1B
        db      0                                              ;#2C4C: 00

CMD_SWITCH_LETTERS:
        ; "   XEWVTSPNLDCBA" — scanned backwards, so A first
        ; Format: FORMAT_STRING
        db      "   XEWVTSPNLDCBA"                             ;#2C4D: 20 20 20 58 45 57 56 54 53 50 4E 4C 44 43 42 41

EXTENSION_TABLE:
        ; Records of len, text, index, 0FFh: .COM=0 .EXE=1 .BAT=2, then "."
        ; Format: FORMAT_HEX
        ; raw
        db      5, 2Eh, 43h, 4Fh                               ;#2C5D
        db      4Dh, 0, 0, 0FFh                                ;#2C61
        db      5, 2Eh, 45h, 58h                               ;#2C65
        db      45h, 0, 1, 0FFh                                ;#2C69
        db      5, 2Eh, 42h, 41h                               ;#2C6D
        db      54h, 0, 2, 0FFh                                ;#2C71
        db      2, 2Eh, 0, 0FFh                                ;#2C75
        db      0, 0                                           ;#2C79

ON_OFF_TABLE:
        ; Same record shape for the ON/OFF keywords: OFF=0, ON=1
        ; Format: FORMAT_HEX
        ; raw
        db      3, 4Fh, 46h, 46h                               ;#2C7B
        db      0, 0FFh, 2, 4Fh                                ;#2C7F
        db      4Eh, 1, 0FFh                                   ;#2C83
        add     [bp+di], al                                    ;#2C86: 00 03
        dec     si                                             ;#2C88: 4E
        dec     di                                             ;#2C89: 4F
        push    sp                                             ;#2C8A: 54
        inc     cx                                             ;#2C8B: 41
        cmp     [di], ax                                       ;#2C8C: 39 05
        inc     bp                                             ;#2C8E: 45
        pop     ax                                             ;#2C8F: 58
        dec     cx                                             ;#2C90: 49
        push    bx                                             ;#2C91: 53
        push    sp                                             ;#2C92: 54
        jns     short 2CCEh                                    ;#2C93: 79 39
        or      al, [di+52h]                                   ;#2C95: 0A 45 52
        push    dx                                             ;#2C98: 52
        dec     di                                             ;#2C99: 4F
        push    dx                                             ;#2C9A: 52
        dec     sp                                             ;#2C9B: 4C
        inc     bp                                             ;#2C9C: 45
        push    si                                             ;#2C9D: 56
        inc     bp                                             ;#2C9E: 45
        dec     sp                                             ;#2C9F: 4C
        dec     dx                                             ;#2CA0: 4A
        cmp     [bx+si], ax                                    ;#2CA1: 39 00
        add     cx, [bx+di+43h]                                ;#2CA3: 03 49 43
        inc     bx                                             ;#2CA6: 43
        inc     bx                                             ;#2CA7: 43
        and     al, 5                                          ;#2CA8: 24 05
        inc     sp                                             ;#2CAA: 44
        dec     cx                                             ;#2CAB: 49
        push    dx                                             ;#2CAC: 52
        inc     bp                                             ;#2CAD: 45
        push    sp                                             ;#2CAE: 54
        push    bp                                             ;#2CAF: 55
        and     al, 3                                          ;#2CB0: 24 03
        inc     sp                                             ;#2CB2: 44
        dec     cx                                             ;#2CB3: 49
        push    dx                                             ;#2CB4: 52
        push    bp                                             ;#2CB5: 55
        and     al, 5                                          ;#2CB6: 24 05
        inc     bp                                             ;#2CB8: 45
        push    dx                                             ;#2CB9: 52
        inc     cx                                             ;#2CBA: 41
        push    bx                                             ;#2CBB: 53
        inc     bp                                             ;#2CBC: 45
        lahf                                                   ;#2CBD: 9F
        daa                                                    ;#2CBE: 27
        add     ax, [di+52h]                                   ;#2CBF: 03 45 52
        inc     cx                                             ;#2CC2: 41
        lahf                                                   ;#2CC3: 9F
        daa                                                    ;#2CC4: 27
        pop     es                                             ;#2CC5: 07
        push    bx                                             ;#2CC6: 53
        push    bp                                             ;#2CC7: 55
        push    ax                                             ;#2CC8: 50
        push    dx                                             ;#2CC9: 52
        dec     cx                                             ;#2CCA: 49
        dec     bp                                             ;#2CCB: 4D
        inc     bp                                             ;#2CCC: 45
        lahf                                                   ;#2CCD: 9F
        daa                                                    ;#2CCE: 27
        add     dx, [bp+di+55h]                                ;#2CCF: 03 53 55
        push    ax                                             ;#2CD2: 50
        lahf                                                   ;#2CD3: 9F
        daa                                                    ;#2CD4: 27
        add     ax, [si+45h]                                   ;#2CD5: 03 44 45
        dec     sp                                             ;#2CD8: 4C
        lahf                                                   ;#2CD9: 9F
        daa                                                    ;#2CDA: 27
        push    es                                             ;#2CDB: 06
        push    dx                                             ;#2CDC: 52
        inc     bp                                             ;#2CDD: 45
        dec     si                                             ;#2CDE: 4E
        inc     cx                                             ;#2CDF: 41
        dec     bp                                             ;#2CE0: 4D
        inc     bp                                             ;#2CE1: 45
        out     28h, al                                        ;#2CE2: E6 28
        or      [bp+si+45h], dl                                ;#2CE4: 08 52 45
        dec     si                                             ;#2CE7: 4E
        dec     di                                             ;#2CE8: 4F
        dec     bp                                             ;#2CE9: 4D
        inc     bp                                             ;#2CEA: 45
        dec     cx                                             ;#2CEB: 49
        inc     cx                                             ;#2CEC: 41
        out     28h, al                                        ;#2CED: E6 28
        add     dx, [bp+si+45h]                                ;#2CEF: 03 52 45
        dec     si                                             ;#2CF2: 4E
        out     28h, al                                        ;#2CF3: E6 28
        add     al, 54h                                        ;#2CF5: 04 54
        pop     cx                                             ;#2CF7: 59
        push    ax                                             ;#2CF8: 50
        inc     bp                                             ;#2CF9: 45
        push    cs                                             ;#2CFA: 0E
        sub     al, 6                                          ;#2CFB: 2C 06
        dec     bp                                             ;#2CFD: 4D
        dec     di                                             ;#2CFE: 4F
        push    bx                                             ;#2CFF: 53
        push    sp                                             ;#2D00: 54
        push    dx                                             ;#2D01: 52
        inc     cx                                             ;#2D02: 41
        push    cs                                             ;#2D03: 0E
        sub     al, 3                                          ;#2D04: 2C 03
        dec     bp                                             ;#2D06: 4D
        dec     di                                             ;#2D07: 4F
        push    bx                                             ;#2D08: 53
        push    cs                                             ;#2D09: 0E
        sub     al, 3                                          ;#2D0A: 2C 03
        push    si                                             ;#2D0C: 56
        dec     di                                             ;#2D0D: 4F
        dec     sp                                             ;#2D0E: 4C
        mov     cs, [si]                                       ;#2D0F: 8E 2C
        add     al, 45h                                        ;#2D11: 04 45
        inc     bx                                             ;#2D13: 43
        dec     ax                                             ;#2D14: 48
        dec     di                                             ;#2D15: 4F
        sub     ax, 32Dh                                       ;#2D16: 2D 2D 03
        inc     bp                                             ;#2D19: 45
        inc     bx                                             ;#2D1A: 43
        dec     di                                             ;#2D1B: 4F
        sub     ax, 52Dh                                       ;#2D1C: 2D 2D 05
        inc     dx                                             ;#2D1F: 42
        push    dx                                             ;#2D20: 52
        inc     bp                                             ;#2D21: 45
        inc     cx                                             ;#2D22: 41
        dec     bx                                             ;#2D23: 4B
        pop     cx                                             ;#2D24: 59
        sub     ax, 5606h                                      ;#2D25: 2D 06 56
        inc     bp                                             ;#2D28: 45
        push    dx                                             ;#2D29: 52
        dec     cx                                             ;#2D2A: 49
        inc     si                                             ;#2D2B: 46
        pop     cx                                             ;#2D2C: 59
        mov     [di], ch                                       ;#2D2D: 88 2D
        pop     es                                             ;#2D2F: 07
        inc     dx                                             ;#2D30: 42
        push    dx                                             ;#2D31: 52
        inc     cx                                             ;#2D32: 41
        push    bx                                             ;#2D33: 53
        inc     bx                                             ;#2D34: 43
        dec     cx                                             ;#2D35: 49
        dec     cx                                             ;#2D36: 49
        lahf                                                   ;#2D37: 9F
        sub     ax, 4F07h                                      ;#2D38: 2D 07 4F
        push    ax                                             ;#2D3B: 50
        push    sp                                             ;#2D3C: 54
        dec     cx                                             ;#2D3D: 49
        dec     di                                             ;#2D3E: 4F
        dec     si                                             ;#2D3F: 4E
        push    bx                                             ;#2D40: 53
        db      0DFh                                           ;#2D41: DF
        sub     ax, 4D04h                                      ;#2D42: 2D 04 4D
        inc     bp                                             ;#2D45: 45
        dec     si                                             ;#2D46: 4E
        push    bp                                             ;#2D47: 55
        add     ch, [4606h]                                    ;#2D48: 02 2E 06 46
        dec     cx                                             ;#2D4C: 49
        dec     sp                                             ;#2D4D: 4C
        push    sp                                             ;#2D4E: 54
        push    dx                                             ;#2D4F: 52
        dec     di                                             ;#2D50: 4F
        or      [5004h], ch                                    ;#2D51: 08 2E 04 50
        inc     cx                                             ;#2D55: 41
        push    sp                                             ;#2D56: 54
        dec     ax                                             ;#2D57: 48
        dec     si                                             ;#2D58: 4E
        push    es                                             ;#2D59: 2E 06
        push    ax                                             ;#2D5B: 50
        push    dx                                             ;#2D5C: 52
        dec     di                                             ;#2D5D: 4F
        dec     bp                                             ;#2D5E: 4D
        push    ax                                             ;#2D5F: 50
        push    sp                                             ;#2D60: 54
        retf    32Eh                                           ;#2D61: CA 2E 03
        push    bx                                             ;#2D64: 53
        inc     bp                                             ;#2D65: 45
        push    sp                                             ;#2D66: 54
        push    es                                             ;#2D67: 06
        das                                                    ;#2D68: 2F
        add     dx, [bp+si+45h]                                ;#2D69: 03 52 45
        dec     bp                                             ;#2D6C: 4D
        pop     ds                                             ;#2D6D: 1F
        xor     [4F43h], al                                    ;#2D6E: 30 06 43 4F
        dec     bp                                             ;#2D72: 4D
        inc     bp                                             ;#2D73: 45
        dec     si                                             ;#2D74: 4E
        push    sp                                             ;#2D75: 54
        pop     ds                                             ;#2D76: 1F
        xor     [bp+di], al                                    ;#2D77: 30 03
        inc     bx                                             ;#2D79: 43
        dec     di                                             ;#2D7A: 4F
        dec     bp                                             ;#2D7B: 4D
        pop     ds                                             ;#2D7C: 1F
        xor     [si], al                                       ;#2D7D: 30 04
        inc     bp                                             ;#2D7F: 45
        pop     ax                                             ;#2D80: 58
        dec     cx                                             ;#2D81: 49
        push    sp                                             ;#2D82: 54
        sub     [bx+si], dh                                    ;#2D83: 28 30
        add     al, 42h                                        ;#2D85: 04 42
        inc     bp                                             ;#2D87: 45
        inc     bp                                             ;#2D88: 45
        push    ax                                             ;#2D89: 50
        xor     [ss:di], al                                    ;#2D8A: 36 30 05
        push    ax                                             ;#2D8D: 50
        inc     cx                                             ;#2D8E: 41
        push    bp                                             ;#2D8F: 55
        push    bx                                             ;#2D90: 53
        inc     bp                                             ;#2D91: 45
        cmp     si, [bx+si]                                    ;#2D92: 3B 30
        add     ax, 4150h                                      ;#2D94: 05 50 41
        push    bp                                             ;#2D97: 55
        push    bx                                             ;#2D98: 53
        inc     cx                                             ;#2D99: 41
        cmp     si, [bx+si]                                    ;#2D9A: 3B 30
        add     dx, [bx+si+41h]                                ;#2D9C: 03 50 41
        push    bp                                             ;#2D9F: 55
        cmp     si, [bx+si]                                    ;#2DA0: 3B 30
        add     dx, [bp+45h]                                   ;#2DA2: 03 56 45
        push    dx                                             ;#2DA5: 52
        db      67h                                            ;#2DA6: 67
        xor     [si], al                                       ;#2DA7: 30 04
        inc     bx                                             ;#2DA9: 43
        push    sp                                             ;#2DAA: 54
        push    sp                                             ;#2DAB: 54
        pop     cx                                             ;#2DAC: 59
        xor     byte [bx+si], 3                                ;#2DAD: 80 30 03
        inc     bx                                             ;#2DB0: 43
        dec     sp                                             ;#2DB1: 4C
        push    bx                                             ;#2DB2: 53
        test    al, 30h                                        ;#2DB3: A8 30
        add     al, 44h                                        ;#2DB5: 04 44
        inc     cx                                             ;#2DB7: 41
        push    sp                                             ;#2DB8: 54
        inc     bp                                             ;#2DB9: 45
        sbb     [bp+si], si                                    ;#2DBA: 19 32
        add     al, 44h                                        ;#2DBC: 04 44
        inc     cx                                             ;#2DBE: 41
        push    sp                                             ;#2DBF: 54
        inc     cx                                             ;#2DC0: 41
        sbb     [bp+si], si                                    ;#2DC1: 19 32
        add     ax, [si+41h]                                   ;#2DC3: 03 44 41
        push    sp                                             ;#2DC6: 54
        sbb     [bp+si], si                                    ;#2DC7: 19 32
        add     al, 54h                                        ;#2DC9: 04 54
        dec     cx                                             ;#2DCB: 49
        dec     bp                                             ;#2DCC: 4D
        inc     bp                                             ;#2DCD: 45
        sbb     [bp+si], si                                    ;#2DCE: 19 32
        add     al, 48h                                        ;#2DD0: 04 48
        dec     di                                             ;#2DD2: 4F
        push    dx                                             ;#2DD3: 52
        inc     cx                                             ;#2DD4: 41
        sbb     [bp+si], si                                    ;#2DD5: 19 32
        add     cx, [bx+si+4Fh]                                ;#2DD7: 03 48 4F
        push    dx                                             ;#2DDA: 52
        sbb     [bp+si], si                                    ;#2DDB: 19 32
        add     ax, 4843h                                      ;#2DDD: 05 43 48
        inc     sp                                             ;#2DE0: 44
        dec     cx                                             ;#2DE1: 49
        push    dx                                             ;#2DE2: 52
        js      short 2E18h                                    ;#2DE3: 78 33
        add     al, [bp+di+44h]                                ;#2DE5: 02 43 44
        js      short 2E1Dh                                    ;#2DE8: 78 33
        add     ax, 4B4Dh                                      ;#2DEA: 05 4D 4B
        inc     sp                                             ;#2DED: 44
        dec     cx                                             ;#2DEE: 49
        push    dx                                             ;#2DEF: 52
        jnle    short 2E25h                                    ;#2DF0: 7F 33
        add     cl, [di+44h]                                   ;#2DF2: 02 4D 44
        jnle    short 2E2Ah                                    ;#2DF5: 7F 33
        add     ax, 4D52h                                      ;#2DF7: 05 52 4D
        inc     sp                                             ;#2DFA: 44
        dec     cx                                             ;#2DFB: 49
        push    dx                                             ;#2DFC: 52
        xchg    [bp+di], dh                                    ;#2DFD: 86 33
        add     dl, [bp+si+44h]                                ;#2DFF: 02 52 44
        xchg    [bp+di], dh                                    ;#2E02: 86 33
        push    es                                             ;#2E04: 06
        inc     cx                                             ;#2E05: 41
        push    ax                                             ;#2E06: 50
        push    ax                                             ;#2E07: 50
        inc     bp                                             ;#2E08: 45
        dec     si                                             ;#2E09: 4E
        inc     sp                                             ;#2E0A: 44
        shl     word [bp+di], cl                               ;#2E0B: D3 33
        add     al, 4Ah                                        ;#2E0D: 04 4A
        dec     di                                             ;#2E0F: 4F
        dec     cx                                             ;#2E10: 49
        dec     si                                             ;#2E11: 4E
        jnp     short 2E4Ah                                    ;#2E12: 7B 36
        add     ax, 5553h                                      ;#2E14: 05 53 55
        inc     dx                                             ;#2E17: 42
        push    bx                                             ;#2E18: 53
        push    sp                                             ;#2E19: 54
        db      0DCh                                           ;#2E1A: DC
        add     al, 43h                                        ;#2E1B: 36 04 43
        dec     ax                                             ;#2E1E: 48
        inc     bx                                             ;#2E1F: 43
        push    ax                                             ;#2E20: 50
        and     dh, [bx]                                       ;#2E21: 22 37
        add     al, 43h                                        ;#2E23: 04 43
        inc     cx                                             ;#2E25: 41
        dec     sp                                             ;#2E26: 4C
        dec     sp                                             ;#2E27: 4C
        sub     [bx], dh                                       ;#2E28: 28 37
        add     ax, [bp+4Fh]                                   ;#2E2A: 03 46 4F
        push    dx                                             ;#2E2D: 52
        aas                                                    ;#2E2E: 3F
        aaa                                                    ;#2E2F: 37
        add     cl, [bx+di+46h]                                ;#2E30: 02 49 46
        push    ds                                             ;#2E33: 1E
        cmp     [di], al                                       ;#2E34: 38 05
        push    bx                                             ;#2E36: 53
        dec     ax                                             ;#2E37: 48
        dec     cx                                             ;#2E38: 49
        inc     si                                             ;#2E39: 46
        push    sp                                             ;#2E3A: 54
        db      0D6h                                           ;#2E3B: D6
        cmp     [si], ax                                       ;#2E3C: 39 04
        inc     di                                             ;#2E3E: 47
        dec     di                                             ;#2E3F: 4F
        push    sp                                             ;#2E40: 54
        dec     di                                             ;#2E41: 4F
        or      ax, 43Ah                                       ;#2E42: 0D 3A 04
        inc     bx                                             ;#2E45: 43
        dec     di                                             ;#2E46: 4F
        push    ax                                             ;#2E47: 50
        pop     cx                                             ;#2E48: 59
        mov     [53Ah], al                                     ;#2E49: A2 3A 05
        inc     bx                                             ;#2E4C: 43
        dec     di                                             ;#2E4D: 4F
        push    ax                                             ;#2E4E: 50
        dec     cx                                             ;#2E4F: 49
        inc     cx                                             ;#2E50: 41
        mov     [33Ah], al                                     ;#2E51: A2 3A 03
        inc     bx                                             ;#2E54: 43
        dec     di                                             ;#2E55: 4F
        push    ax                                             ;#2E56: 50
        mov     [3Ah], al                                      ;#2E57: A2 3A 00
        cli                                                    ;#2E5A: FA
        push    cs                                             ;#2E5B: 0E
        pop     ss                                             ;#2E5C: 17
        mov     sp, 4F70h                                      ;#2E5D: BC 70 4F
        sti                                                    ;#2E60: FB
        push    cs                                             ;#2E61: 0E
        pop     es                                             ;#2E62: 07
        mov     ax, 180Eh                                      ;#2E63: B8 0E 18
        int     21h                                            ;#2E66: CD 21
        mov     ah, 19h                                        ;#2E68: B4 19
        int     21h                                            ;#2E6A: CD 21
        mov     [cs:4706h], al                                 ;#2E6C: 2E A2 06 47
        mov     dl, al                                         ;#2E70: 8A D0
        mov     ah, 0Eh                                        ;#2E72: B4 0E
        int     21h                                            ;#2E74: CD 21
        mov     [cs:4707h], al                                 ;#2E76: 2E A2 07 47
        call    near 3E95h                                     ;#2E7A: E8 18 10
        jb      short 2EADh                                    ;#2E7D: 72 2E
        call    near 3F8Eh                                     ;#2E7F: E8 0C 11
        jb      short 2EADh                                    ;#2E82: 72 29
        xor     ax, ax                                         ;#2E84: 33 C0
        mov     [38Eh], al                                     ;#2E86: A2 8E 03
        mov     [33Dh], ax                                     ;#2E89: A3 3D 03
        call    near 3FD9h                                     ;#2E8C: E8 4A 11
        jb      short 2E99h                                    ;#2E8F: 72 08
        call    near 4215h                                     ;#2E91: E8 81 13
        jb      short 2E99h                                    ;#2E94: 72 03
        call    near 423Bh                                     ;#2E96: E8 A2 13
        push    cs                                             ;#2E99: 0E
        pop     ds                                             ;#2E9A: 1F
        mov     es, [4660h]                                    ;#2E9B: 8E 06 60 46
        call    near 3BC3h                                     ;#2E9F: E8 21 0D
        test    byte [es:339h], 2                              ;#2EA2: 26 F6 06 39 03 02
        jz      short 2EADh                                    ;#2EA8: 74 03
        jmp     near 3DD6h                                     ;#2EAA: E9 29 0F
        push    cs                                             ;#2EAD: 0E
        pop     ds                                             ;#2EAE: 1F
        push    cs                                             ;#2EAF: 0E
        pop     es                                             ;#2EB0: 07
        mov     si, 4664h                                      ;#2EB1: BE 64 46
        call    near 2F0Bh                                     ;#2EB4: E8 54 00
        jz      short 2EFDh                                    ;#2EB7: 74 44
        cmp     al, 3Bh                                        ;#2EB9: 3C 3B
        jz      short 2EFDh                                    ;#2EBB: 74 40
        call    near 3CA9h                                     ;#2EBD: E8 E9 0D
        call    near 4253h                                     ;#2EC0: E8 90 13
        mov     [472Bh], si                                    ;#2EC3: 89 36 2B 47
        call    near 4262h                                     ;#2EC7: E8 98 13
        jb      short 2EE6h                                    ;#2ECA: 72 1A
        mov     si, [472Bh]                                    ;#2ECC: 8B 36 2B 47
        mov     byte [4E62h], 0                                ;#2ED0: C6 06 62 4E 00
        call    near 4284h                                     ;#2ED5: E8 AC 13
        mov     si, [472Bh]                                    ;#2ED8: 8B 36 2B 47
        call    near 42ACh                                     ;#2EDC: E8 CD 13
        jnb     short 2ED5h                                    ;#2EDF: 73 F4
        mov     dx, COMMAND_ENTRY                              ;#2EE1: BA 00 01
        jmp     short 2EE9h                                    ;#2EE4: EB 03
        mov     dx, 141h                                       ;#2EE6: BA 41 01
        mov     ds, [cs:4660h]                                 ;#2EE9: 2E 8E 1E 60 46
        and     byte [339h], 0FCh                              ;#2EEE: 80 26 39 03 FC
        or      byte [336h], 3                                 ;#2EF3: 80 0E 36 03 03
        push    cs                                             ;#2EF8: 0E
        pop     ds                                             ;#2EF9: 1F
        call    near 39FDh                                     ;#2EFA: E8 00 0B
        jmp     near 503Fh                                     ;#2EFD: E9 3F 21
        cmp     al, 61h                                        ;#2F00: 3C 61
        jb      short 2F0Ah                                    ;#2F02: 72 06
        cmp     al, 7Ah                                        ;#2F04: 3C 7A
        jnbe    short 2F0Ah                                    ;#2F06: 77 02
        sub     al, 20h                                        ;#2F08: 2C 20
        ret                                                    ;#2F0A: C3
        lodsb                                                  ;#2F0B: AC
        cmp     al, 20h                                        ;#2F0C: 3C 20
        jz      short 2F0Bh                                    ;#2F0E: 74 FB
        cmp     al, 9                                          ;#2F10: 3C 09
        jz      short 2F0Bh                                    ;#2F12: 74 F7
        dec     si                                             ;#2F14: 4E
        cmp     al, 0Dh                                        ;#2F15: 3C 0D
        ret                                                    ;#2F17: C3
        call    near 2F60h                                     ;#2F18: E8 45 00
        jz      short 2F5Fh                                    ;#2F1B: 74 42
        cmp     al, 3Ah                                        ;#2F1D: 3C 3A
        jz      short 2F5Fh                                    ;#2F1F: 74 3E
        cmp     al, 2Eh                                        ;#2F21: 3C 2E
        jz      short 2F5Fh                                    ;#2F23: 74 3A
        cmp     al, [cs:4662h]                                 ;#2F25: 2E 3A 06 62 46
        jz      short 2F5Eh                                    ;#2F2A: 74 32
        cmp     al, 2Fh                                        ;#2F2C: 3C 2F
        jz      short 2F5Eh                                    ;#2F2E: 74 2E
        cmp     al, 3Dh                                        ;#2F30: 3C 3D
        jz      short 2F5Eh                                    ;#2F32: 74 2A
        cmp     al, 2Ch                                        ;#2F34: 3C 2C
        jz      short 2F5Eh                                    ;#2F36: 74 26
        cmp     al, 3Bh                                        ;#2F38: 3C 3B
        jz      short 2F5Eh                                    ;#2F3A: 74 22
        cmp     al, 2Bh                                        ;#2F3C: 3C 2B
        jz      short 2F5Eh                                    ;#2F3E: 74 1E
        cmp     al, 5Bh                                        ;#2F40: 3C 5B
        jz      short 2F5Eh                                    ;#2F42: 74 1A
        cmp     al, 5Dh                                        ;#2F44: 3C 5D
        jz      short 2F5Eh                                    ;#2F46: 74 16
        cmp     al, 22h                                        ;#2F48: 3C 22
        jz      short 2F5Eh                                    ;#2F4A: 74 12
        cmp     al, 7Ch                                        ;#2F4C: 3C 7C
        jz      short 2F5Eh                                    ;#2F4E: 74 0E
        cmp     al, 3Ch                                        ;#2F50: 3C 3C
        jz      short 2F5Eh                                    ;#2F52: 74 0A
        cmp     al, 3Eh                                        ;#2F54: 3C 3E
        jz      short 2F5Eh                                    ;#2F56: 74 06
        cmp     al, 20h                                        ;#2F58: 3C 20
        jnbe    short 2F5Fh                                    ;#2F5A: 77 03
        cmp     al, al                                         ;#2F5C: 3A C0
        stc                                                    ;#2F5E: F9
        ret                                                    ;#2F5F: C3
        cmp     al, 5Ch                                        ;#2F60: 3C 5C
        jz      short 2F6Dh                                    ;#2F62: 74 09
        cmp     al, [cs:4663h]                                 ;#2F64: 2E 3A 06 63 46
        jnz     short 2F6Dh                                    ;#2F69: 75 02
        mov     al, 5Ch                                        ;#2F6B: B0 5C
        ret                                                    ;#2F6D: C3
        cmp     al, [cs:4663h]                                 ;#2F6E: 2E 3A 06 63 46
        jz      short 2F77h                                    ;#2F73: 74 02
        cmp     al, 5Ch                                        ;#2F75: 3C 5C
        ret                                                    ;#2F77: C3
        xor     cx, cx                                         ;#2F78: 33 C9
        lodsb                                                  ;#2F7A: AC
        call    near 2F00h                                     ;#2F7B: E8 82 FF
        stosb                                                  ;#2F7E: AA
        inc     cx                                             ;#2F7F: 41
        cmp     al, 0Dh                                        ;#2F80: 3C 0D
        jnz     short 2F7Ah                                    ;#2F82: 75 F6
        dec     cx                                             ;#2F84: 49
        ret                                                    ;#2F85: C3
        xor     cx, cx                                         ;#2F86: 33 C9
        lodsb                                                  ;#2F88: AC
        call    near 2F00h                                     ;#2F89: E8 74 FF
        stosb                                                  ;#2F8C: AA
        inc     cx                                             ;#2F8D: 41
        or      al, al                                         ;#2F8E: 0A C0
        jnz     short 2F88h                                    ;#2F90: 75 F6
        dec     cx                                             ;#2F92: 49
        ret                                                    ;#2F93: C3
        xor     cx, cx                                         ;#2F94: 33 C9
        lodsb                                                  ;#2F96: AC
        stosb                                                  ;#2F97: AA
        inc     cx                                             ;#2F98: 41
        cmp     al, 0Dh                                        ;#2F99: 3C 0D
        jnz     short 2F96h                                    ;#2F9B: 75 F9
        dec     cx                                             ;#2F9D: 49
        ret                                                    ;#2F9E: C3
        xor     cx, cx                                         ;#2F9F: 33 C9
        mov     al, [bp]                                       ;#2FA1: 8A 46 00
        inc     bp                                             ;#2FA4: 45
        stosb                                                  ;#2FA5: AA
        inc     cx                                             ;#2FA6: 41
        cmp     al, 0Dh                                        ;#2FA7: 3C 0D
        jnz     short 2FA1h                                    ;#2FA9: 75 F6
        dec     cx                                             ;#2FAB: 49
        ret                                                    ;#2FAC: C3
        xor     cx, cx                                         ;#2FAD: 33 C9
        lodsb                                                  ;#2FAF: AC
        stosb                                                  ;#2FB0: AA
        inc     cx                                             ;#2FB1: 41
        or      al, al                                         ;#2FB2: 0A C0
        jnz     short 2FAFh                                    ;#2FB4: 75 F9
        dec     cx                                             ;#2FB6: 49
        ret                                                    ;#2FB7: C3
        scasb                                                  ;#2FB8: AE
        jz      short 2FC5h                                    ;#2FB9: 74 0A
        cmp     [es:di-1], ah                                  ;#2FBB: 26 38 65 FF
        jnz     short 2FB8h                                    ;#2FBF: 75 F7
        cmp     [es:di-1], al                                  ;#2FC1: 26 38 45 FF
        ret                                                    ;#2FC5: C3
        mov     al, 0                                          ;#2FC6: B0 00
        cmp     [es:di], al                                    ;#2FC8: 26 38 05
        jnz     short 2FCFh                                    ;#2FCB: 75 02
        stc                                                    ;#2FCD: F9
        ret                                                    ;#2FCE: C3
        push    si                                             ;#2FCF: 56
        push    di                                             ;#2FD0: 57
        push    cx                                             ;#2FD1: 51
        rep     cmpsb                                          ;#2FD2: F3 A6
        pop     cx                                             ;#2FD4: 59
        pop     di                                             ;#2FD5: 5F
        pop     si                                             ;#2FD6: 5E
        jnz     short 2FDBh                                    ;#2FD7: 75 02
        clc                                                    ;#2FD9: F8
        ret                                                    ;#2FDA: C3
        scasb                                                  ;#2FDB: AE
        jnz     short 2FDBh                                    ;#2FDC: 75 FD
        jmp     short 2FC6h                                    ;#2FDE: EB E6
        cmp     al, 2Ah                                        ;#2FE0: 3C 2A
        jz      short 2FE6h                                    ;#2FE2: 74 02
        cmp     al, 3Fh                                        ;#2FE4: 3C 3F
        ret                                                    ;#2FE6: C3
        cmp     al, 22h                                        ;#2FE7: 3C 22
        jz      short 2FF5h                                    ;#2FE9: 74 0A
        cmp     al, 3Eh                                        ;#2FEB: 3C 3E
        jz      short 2FF5h                                    ;#2FED: 74 06
        cmp     al, 3Ch                                        ;#2FEF: 3C 3C
        jz      short 2FF5h                                    ;#2FF1: 74 02
        cmp     al, 7Ch                                        ;#2FF3: 3C 7C
        ret                                                    ;#2FF5: C3
        cmp     al, 0Dh                                        ;#2FF6: 3C 0D
        jz      short 2FFFh                                    ;#2FF8: 74 05
        cmp     al, [cs:4662h]                                 ;#2FFA: 2E 3A 06 62 46
        ret                                                    ;#2FFF: C3
        cmp     al, 0Dh                                        ;#3000: 3C 0D
        jz      short 300Ah                                    ;#3002: 74 06
        cmp     al, 20h                                        ;#3004: 3C 20
        jz      short 300Ah                                    ;#3006: 74 02
        cmp     al, 9                                          ;#3008: 3C 09
        ret                                                    ;#300A: C3
        cmp     al, 3Bh                                        ;#300B: 3C 3B
        jz      short 301Dh                                    ;#300D: 74 0E
        cmp     al, 3Dh                                        ;#300F: 3C 3D
        jz      short 301Dh                                    ;#3011: 74 0A
        cmp     al, 2Ch                                        ;#3013: 3C 2C
        jz      short 301Dh                                    ;#3015: 74 06
        cmp     al, 20h                                        ;#3017: 3C 20
        jz      short 301Dh                                    ;#3019: 74 02
        cmp     al, 9                                          ;#301B: 3C 09
        ret                                                    ;#301D: C3
        inc     bp                                             ;#301E: 45
        mov     al, [bp]                                       ;#301F: 8A 46 00
        call    near 3004h                                     ;#3022: E8 DF FF
        jz      short 301Eh                                    ;#3025: 74 F7
        cmp     al, 0Dh                                        ;#3027: 3C 0D
        ret                                                    ;#3029: C3
        lodsb                                                  ;#302A: AC
        call    near 300Bh                                     ;#302B: E8 DD FF
        jz      short 302Ah                                    ;#302E: 74 FA
        dec     si                                             ;#3030: 4E
        cmp     al, 0Dh                                        ;#3031: 3C 0D
        ret                                                    ;#3033: C3
        test    byte [si+15h], 10h                             ;#3034: F6 44 15 10
        clc                                                    ;#3038: F8
        jz      short 304Fh                                    ;#3039: 74 14
        cmp     byte [si+1Eh], 2Eh                             ;#303B: 80 7C 1E 2E
        stc                                                    ;#303F: F9
        jnz     short 304Fh                                    ;#3040: 75 0D
        cmp     byte [si+1Fh], 0                               ;#3042: 80 7C 1F 00
        jz      short 304Fh                                    ;#3046: 74 07
        cmp     word [si+1Fh], 2Eh                             ;#3048: 83 7C 1F 2E
        jz      short 304Fh                                    ;#304C: 74 01
        stc                                                    ;#304E: F9
        ret                                                    ;#304F: C3
        lodsb                                                  ;#3050: AC
        or      al, al                                         ;#3051: 0A C0
        jz      short 3059h                                    ;#3053: 74 04
        cmp     al, 2Eh                                        ;#3055: 3C 2E
        jnz     short 3050h                                    ;#3057: 75 F7
        or      al, al                                         ;#3059: 0A C0
        ret                                                    ;#305B: C3
        mov     dx, 47DAh                                      ;#305C: BA DA 47
        mov     ah, 1Ah                                        ;#305F: B4 1A
        int     21h                                            ;#3061: CD 21
        ret                                                    ;#3063: C3
        push    es                                             ;#3064: 06
        mov     es, [cs:4660h]                                 ;#3065: 2E 8E 06 60 46
        xor     ax, ax                                         ;#306A: 33 C0
        xchg    [es:272h], ax                                  ;#306C: 26 87 06 72 02
        mov     es, ax                                         ;#3071: 8E C0
        mov     ah, 49h                                        ;#3073: B4 49
        int     21h                                            ;#3075: CD 21
        pop     es                                             ;#3077: 07
        ret                                                    ;#3078: C3
        mov     bx, 0FFFFh                                     ;#3079: BB FF FF
        mov     ah, 48h                                        ;#307C: B4 48
        int     21h                                            ;#307E: CD 21
        mov     ah, 48h                                        ;#3080: B4 48
        int     21h                                            ;#3082: CD 21
        mov     [es:272h], ax                                  ;#3084: 26 A3 72 02
        mov     bx, cs                                         ;#3088: 8C CB
        sub     bx, ax                                         ;#308A: 2B D8
        mov     [es:274h], bx                                  ;#308C: 26 89 1E 74 02
        mov     bx, ax                                         ;#3091: 8B D8
        ret                                                    ;#3093: C3
        push    ds                                             ;#3094: 1E
        push    es                                             ;#3095: 06
        call    near 3064h                                     ;#3096: E8 CB FF
        mov     bx, 629h                                       ;#3099: BB 29 06
        sub     bx, 337h                                       ;#309C: 81 EB 37 03
        add     bx, 0Fh                                        ;#30A0: 83 C3 0F
        mov     cl, 4                                          ;#30A3: B1 04
        shr     bx, cl                                         ;#30A5: D3 EB
        mov     ds, [cs:4660h]                                 ;#30A7: 2E 8E 1E 60 46
        cmp     bx, [274h]                                     ;#30AC: 3B 1E 74 02
        cmc                                                    ;#30B0: F5
        jb      short 30E7h                                    ;#30B1: 72 34
        mov     ah, 48h                                        ;#30B3: B4 48
        int     21h                                            ;#30B5: CD 21
        jb      short 30E7h                                    ;#30B7: 72 2E
        mov     es, ax                                         ;#30B9: 8E C0
        xor     di, di                                         ;#30BB: 33 FF
        mov     si, 337h                                       ;#30BD: BE 37 03
        mov     cx, 629h                                       ;#30C0: B9 29 06
        sub     cx, si                                         ;#30C3: 2B CE
        rep     movsb                                          ;#30C5: F3 A4
        mov     [337h], es                                     ;#30C7: 8C 06 37 03
        xor     al, al                                         ;#30CB: 32 C0
        mov     [33Dh], al                                     ;#30CD: A2 3D 03
        mov     [33Eh], al                                     ;#30D0: A2 3E 03
        mov     [38Eh], al                                     ;#30D3: A2 8E 03
        mov     [33Ah], al                                     ;#30D6: A2 3A 03
        mov     al, 0FFh                                       ;#30D9: B0 FF
        mov     [33Bh], al                                     ;#30DB: A2 3B 03
        mov     [33Ch], al                                     ;#30DE: A2 3C 03
        mov     byte [339h], 10h                               ;#30E1: C6 06 39 03 10
        clc                                                    ;#30E6: F8
        pushf                                                  ;#30E7: 9C
        mov     es, [cs:4660h]                                 ;#30E8: 2E 8E 06 60 46
        call    near 3079h                                     ;#30ED: E8 89 FF
        popf                                                   ;#30F0: 9D
        pop     es                                             ;#30F1: 07
        pop     ds                                             ;#30F2: 1F
        ret                                                    ;#30F3: C3
        mov     bp, cx                                         ;#30F4: 8B E9
        call    near 311Ch                                     ;#30F6: E8 23 00
        jb      short 311Bh                                    ;#30F9: 72 20
        push    ds                                             ;#30FB: 1E
        push    es                                             ;#30FC: 06
        pop     ds                                             ;#30FD: 1F
        mov     si, di                                         ;#30FE: 8B F7
        call    near 3135h                                     ;#3100: E8 32 00
        push    si                                             ;#3103: 56
        jz      short 310Bh                                    ;#3104: 74 05
        call    near 3135h                                     ;#3106: E8 2C 00
        jnz     short 3106h                                    ;#3109: 75 FB
        pop     cx                                             ;#310B: 59
        sub     si, cx                                         ;#310C: 2B F1
        xchg    cx, si                                         ;#310E: 87 F1
        inc     cx                                             ;#3110: 41
        rep     movsb                                          ;#3111: F3 A4
        dec     di                                             ;#3113: 4F
        jnz     short 311Ah                                    ;#3114: 75 04
        mov     byte [di+1], 0                                 ;#3116: C6 45 01 00
        pop     ds                                             ;#311A: 1F
        ret                                                    ;#311B: C3
        mov     es, [4660h]                                    ;#311C: 8E 06 60 46
        mov     es, [es:2Ch]                                   ;#3120: 26 8E 06 2C 00
        xor     di, di                                         ;#3125: 33 FF
        jmp     near 2FC6h                                     ;#3127: E9 9C FE
        cmp     si, di                                         ;#312A: 3B F7
        jbe     short 3134h                                    ;#312C: 76 06
        lodsb                                                  ;#312E: AC
        stosb                                                  ;#312F: AA
        cmp     al, 0Dh                                        ;#3130: 3C 0D
        jnz     short 312Eh                                    ;#3132: 75 FA
        ret                                                    ;#3134: C3
        xor     ah, ah                                         ;#3135: 32 E4
        lodsb                                                  ;#3137: AC
        cmp     al, ah                                         ;#3138: 3A C4
        jnz     short 3137h                                    ;#313A: 75 FB
        cmp     byte [si], 0                                   ;#313C: 80 3C 00
        ret                                                    ;#313F: C3
        push    bp                                             ;#3140: 55
        push    ax                                             ;#3141: 50
        push    si                                             ;#3142: 56
        mov     bp, sp                                         ;#3143: 8B EC
        mov     si, [bp]                                       ;#3145: 8B 76 00
        xor     ch, ch                                         ;#3148: 32 ED
        mov     cl, [es:di]                                    ;#314A: 26 8A 0D
        inc     di                                             ;#314D: 47
        jcxz    3166h                                          ;#314E: E3 16
        lodsb                                                  ;#3150: AC
        call    near 2F00h                                     ;#3151: E8 AC FD
        inc     di                                             ;#3154: 47
        cmp     al, [es:di-1]                                  ;#3155: 26 3A 45 FF
        loope   3150h                                          ;#3159: E1 F5
        lahf                                                   ;#315B: 9F
        add     di, cx                                         ;#315C: 03 F9
        mov     cx, [es:di]                                    ;#315E: 26 8B 0D
        inc     di                                             ;#3161: 47
        inc     di                                             ;#3162: 47
        sahf                                                   ;#3163: 9E
        jnz     short 3145h                                    ;#3164: 75 DF
        pop     ax                                             ;#3166: 58
        pop     ax                                             ;#3167: 58
        pop     bp                                             ;#3168: 5D
        ret                                                    ;#3169: C3
        cmp     byte [si], 22h                                 ;#316A: 80 3C 22
        jnz     short 3188h                                    ;#316D: 75 19
        push    ax                                             ;#316F: 50
        push    di                                             ;#3170: 57
        push    si                                             ;#3171: 56
        push    cx                                             ;#3172: 51
        inc     si                                             ;#3173: 46
        lodsb                                                  ;#3174: AC
        cmp     al, 0Dh                                        ;#3175: 3C 0D
        jz      short 3191h                                    ;#3177: 74 18
        cmp     al, 22h                                        ;#3179: 3C 22
        jnz     short 3182h                                    ;#317B: 75 05
        lodsb                                                  ;#317D: AC
        cmp     al, 22h                                        ;#317E: 3C 22
        jnz     short 3199h                                    ;#3180: 75 17
        jcxz    318Ch                                          ;#3182: E3 08
        stosb                                                  ;#3184: AA
        dec     cx                                             ;#3185: 49
        jmp     short 3174h                                    ;#3186: EB EC
        xor     cx, cx                                         ;#3188: 33 C9
        stc                                                    ;#318A: F9
        ret                                                    ;#318B: C3
        mov     cx, 1                                          ;#318C: B9 01 00
        jmp     short 3194h                                    ;#318F: EB 03
        mov     cx, 2                                          ;#3191: B9 02 00
        pop     ax                                             ;#3194: 58
        pop     si                                             ;#3195: 5E
        stc                                                    ;#3196: F9
        jmp     short 31A1h                                    ;#3197: EB 08
        dec     si                                             ;#3199: 4E
        mov     ax, cx                                         ;#319A: 8B C1
        pop     cx                                             ;#319C: 59
        sub     cx, ax                                         ;#319D: 2B C8
        pop     ax                                             ;#319F: 58
        clc                                                    ;#31A0: F8
        pop     di                                             ;#31A1: 5F
        pop     ax                                             ;#31A2: 58
        ret                                                    ;#31A3: C3
        push    bp                                             ;#31A4: 55
        push    cx                                             ;#31A5: 51
        push    bx                                             ;#31A6: 53
        mov     bx, ax                                         ;#31A7: 8B D8
        xor     ax, ax                                         ;#31A9: 33 C0
        push    ax                                             ;#31AB: 50
        pushf                                                  ;#31AC: 9C
        mov     bp, sp                                         ;#31AD: 8B EC
        or      byte [bp], 40h                                 ;#31AF: 80 4E 00 40
        call    near 2F0Bh                                     ;#31B3: E8 55 FD
        jz      short 31C3h                                    ;#31B6: 74 0B
        and     byte [bp], 0BFh                                ;#31B8: 80 66 00 BF
        cmp     al, [cs:4662h]                                 ;#31BC: 2E 3A 06 62 46
        jz      short 31C9h                                    ;#31C1: 74 06
        popf                                                   ;#31C3: 9D
        pop     ax                                             ;#31C4: 58
        pop     bx                                             ;#31C5: 5B
        pop     cx                                             ;#31C6: 59
        pop     bp                                             ;#31C7: 5D
        ret                                                    ;#31C8: C3
        inc     si                                             ;#31C9: 46
        call    near 2F0Bh                                     ;#31CA: E8 3E FD
        jz      short 31EAh                                    ;#31CD: 74 1B
        call    near 2F00h                                     ;#31CF: E8 2E FD
        inc     si                                             ;#31D2: 46
        push    di                                             ;#31D3: 57
        mov     cx, 10h                                        ;#31D4: B9 10 00
        repne   scasb                                          ;#31D7: F2 AE
        pop     di                                             ;#31D9: 5F
        jnz     short 31EAh                                    ;#31DA: 75 0E
        mov     ax, 1                                          ;#31DC: B8 01 00
        shl     ax, cl                                         ;#31DF: D3 E0
        test    ax, bx                                         ;#31E1: 85 D8
        jz      short 31EAh                                    ;#31E3: 74 05
        or      [bp+2], ax                                     ;#31E5: 09 46 02
        jmp     short 31AFh                                    ;#31E8: EB C5
        or      byte [bp], 1                                   ;#31EA: 80 4E 00 01
        jmp     short 31AFh                                    ;#31EE: EB BF
        xor     ax, ax                                         ;#31F0: 33 C0
        push    es                                             ;#31F2: 06
        push    di                                             ;#31F3: 57
        push    ds                                             ;#31F4: 1E
        push    si                                             ;#31F5: 56
        push    cs                                             ;#31F6: 0E
        pop     es                                             ;#31F7: 07
        mov     di, 0C2Dh                                      ;#31F8: BF 2D 0C
        push    ss                                             ;#31FB: 16
        pop     ds                                             ;#31FC: 1F
        mov     si, bp                                         ;#31FD: 8B F5
        call    near 31A4h                                     ;#31FF: E8 A2 FF
        mov     bp, si                                         ;#3202: 8B EE
        pop     si                                             ;#3204: 5E
        pop     ds                                             ;#3205: 1F
        pop     di                                             ;#3206: 5F
        pop     es                                             ;#3207: 07
        ret                                                    ;#3208: C3
        push    dx                                             ;#3209: 52
        push    cx                                             ;#320A: 51
        mov     dx, di                                         ;#320B: 8B D7
        mov     cx, COMMAND_ENTRY                              ;#320D: B9 00 01
        xor     al, al                                         ;#3210: 32 C0
        repne   scasb                                          ;#3212: F2 AE
        mov     al, [es:di-1]                                  ;#3214: 26 8A 45 FF
        call    near 2F6Eh                                     ;#3218: E8 53 FD
        jz      short 3226h                                    ;#321B: 74 09
        cmp     al, 3Ah                                        ;#321D: 3C 3A
        jz      short 3226h                                    ;#321F: 74 05
        dec     di                                             ;#3221: 4F
        cmp     di, dx                                         ;#3222: 3B FA
        jnbe    short 3214h                                    ;#3224: 77 EE
        pop     cx                                             ;#3226: 59
        pop     dx                                             ;#3227: 5A
        ret                                                    ;#3228: C3
        mov     ah, 2                                          ;#3229: B4 02
        push    bx                                             ;#322B: 53
        push    cx                                             ;#322C: 51
        call    near 3251h                                     ;#322D: E8 21 00
        jb      short 324Eh                                    ;#3230: 72 1C
        mov     dx, cx                                         ;#3232: 8B D1
        inc     bp                                             ;#3234: 45
        call    near 3251h                                     ;#3235: E8 19 00
        cmc                                                    ;#3238: F5
        jnb     short 324Eh                                    ;#3239: 73 13
        dec     ah                                             ;#323B: FE CC
        stc                                                    ;#323D: F9
        jz      short 324Eh                                    ;#323E: 74 0E
        mov     bx, dx                                         ;#3240: 8B DA
        shl     dx, 1                                          ;#3242: D1 E2
        shl     dx, 1                                          ;#3244: D1 E2
        add     dx, bx                                         ;#3246: 03 D3
        shl     dx, 1                                          ;#3248: D1 E2
        add     dx, cx                                         ;#324A: 03 D1
        jmp     short 3234h                                    ;#324C: EB E6
        pop     cx                                             ;#324E: 59
        pop     bx                                             ;#324F: 5B
        ret                                                    ;#3250: C3
        mov     al, [bp]                                       ;#3251: 8A 46 00
        sub     al, 30h                                        ;#3254: 2C 30
        jb      short 325Fh                                    ;#3256: 72 07
        cmp     al, 0Ah                                        ;#3258: 3C 0A
        cmc                                                    ;#325A: F5
        mov     ch, 0                                          ;#325B: B5 00
        mov     cl, al                                         ;#325D: 8A C8
        ret                                                    ;#325F: C3
        cbw                                                    ;#3260: 98
        add     si, ax                                         ;#3261: 03 F0
        shl     ax, 1                                          ;#3263: D1 E0
        add     si, ax                                         ;#3265: 03 F0
        movsw                                                  ;#3267: A5
        movsb                                                  ;#3268: A4
        ret                                                    ;#3269: C3
        aam                                                    ;#326A: D4 0A
        or      ax, 3030h                                      ;#326C: 0D 30 30
        xchg    al, ah                                         ;#326F: 86 E0
        cmp     al, 30h                                        ;#3271: 3C 30
        jnz     short 3277h                                    ;#3273: 75 02
        sub     al, bh                                         ;#3275: 2A C7
        mov     bh, 0                                          ;#3277: B7 00
        stosw                                                  ;#3279: AB
        ret                                                    ;#327A: C3
        xor     al, al                                         ;#327B: 32 C0
        xor     bx, bx                                         ;#327D: 33 DB
        xor     dx, dx                                         ;#327F: 33 D2
        mov     cx, 20h                                        ;#3281: B9 20 00
        shl     si, 1                                          ;#3284: D1 E6
        rcl     di, 1                                          ;#3286: D1 D7
        xchg    ax, dx                                         ;#3288: 92
        call    near 32DEh                                     ;#3289: E8 52 00
        xchg    ax, dx                                         ;#328C: 92
        xchg    ax, bx                                         ;#328D: 93
        call    near 32DEh                                     ;#328E: E8 4D 00
        xchg    ax, bx                                         ;#3291: 93
        adc     al, al                                         ;#3292: 12 C0
        daa                                                    ;#3294: 27
        loop    3284h                                          ;#3295: E2 ED
        mov     di, 470Bh                                      ;#3297: BF 0B 47
        mov     cx, 1019h                                      ;#329A: B9 19 10
        call    near 32C1h                                     ;#329D: E8 21 00
        mov     al, bh                                         ;#32A0: 8A C7
        call    near 32C1h                                     ;#32A2: E8 1C 00
        mov     al, bl                                         ;#32A5: 8A C3
        call    near 32C1h                                     ;#32A7: E8 17 00
        mov     al, dh                                         ;#32AA: 8A C6
        call    near 32C1h                                     ;#32AC: E8 12 00
        mov     al, dl                                         ;#32AF: 8A C2
        call    near 32C1h                                     ;#32B1: E8 0D 00
        xor     al, al                                         ;#32B4: 32 C0
        stosb                                                  ;#32B6: AA
        xchg    al, ah                                         ;#32B7: 86 E0
        stc                                                    ;#32B9: F9
        sbb     di, ax                                         ;#32BA: 1B F8
        mov     dx, di                                         ;#32BC: 8B D7
        jmp     near 39E4h                                     ;#32BE: E9 23 07
        push    ax                                             ;#32C1: 50
        shr     al, 1                                          ;#32C2: D0 E8
        shr     al, 1                                          ;#32C4: D0 E8
        shr     al, 1                                          ;#32C6: D0 E8
        shr     al, 1                                          ;#32C8: D0 E8
        call    near 32CEh                                     ;#32CA: E8 01 00
        pop     ax                                             ;#32CD: 58
        and     al, 0Fh                                        ;#32CE: 24 0F
        jz      short 32D4h                                    ;#32D0: 74 02
        xor     ch, ch                                         ;#32D2: 32 ED
        add     al, 30h                                        ;#32D4: 04 30
        dec     cl                                             ;#32D6: FE C9
        and     ch, cl                                         ;#32D8: 22 E9
        sub     al, ch                                         ;#32DA: 2A C5
        stosb                                                  ;#32DC: AA
        ret                                                    ;#32DD: C3
        adc     al, al                                         ;#32DE: 12 C0
        daa                                                    ;#32E0: 27
        xchg    ah, al                                         ;#32E1: 86 C4
        adc     al, al                                         ;#32E3: 12 C0
        daa                                                    ;#32E5: 27
        xchg    al, ah                                         ;#32E6: 86 E0
        ret                                                    ;#32E8: C3
        push    es                                             ;#32E9: 06
        push    di                                             ;#32EA: 57
        push    si                                             ;#32EB: 56
        push    ax                                             ;#32EC: 50
        push    ds                                             ;#32ED: 1E
        pop     es                                             ;#32EE: 07
        mov     si, 4708h                                      ;#32EF: BE 08 47
        mov     di, 4E3Dh                                      ;#32F2: BF 3D 4E
        add     al, 41h                                        ;#32F5: 04 41
        mov     [si], al                                       ;#32F7: 88 04
        mov     word [si+1], 0D3Ah                             ;#32F9: C7 44 01 3A 0D
        mov     ax, 2901h                                      ;#32FE: B8 01 29
        int     21h                                            ;#3301: CD 21
        or      al, al                                         ;#3303: 0A C0
        pop     ax                                             ;#3305: 58
        pop     si                                             ;#3306: 5E
        pop     di                                             ;#3307: 5F
        pop     es                                             ;#3308: 07
        ret                                                    ;#3309: C3
        xor     al, al                                         ;#330A: 32 C0
        mov     [472Dh], al                                    ;#330C: A2 2D 47
        mov     [472Eh], al                                    ;#330F: A2 2E 47
        mov     [472Fh], di                                    ;#3312: 89 3E 2F 47
        mov     dx, di                                         ;#3316: 8B D7
        add     dx, 50h                                        ;#3318: 83 C2 50
        mov     ax, [bp]                                       ;#331B: 8B 46 00
        cmp     al, 0Dh                                        ;#331E: 3C 0D
        jz      short 334Dh                                    ;#3320: 74 2B
        cmp     ah, 3Ah                                        ;#3322: 80 FC 3A
        jnz     short 334Dh                                    ;#3325: 75 26
        or      byte [472Dh], 11h                              ;#3327: 80 0E 2D 47 11
        inc     bp                                             ;#332C: 45
        inc     bp                                             ;#332D: 45
        stosw                                                  ;#332E: AB
        mov     [472Fh], di                                    ;#332F: 89 3E 2F 47
        call    near 2F00h                                     ;#3333: E8 CA FB
        sub     al, 40h                                        ;#3336: 2C 40
        mov     [472Eh], al                                    ;#3338: A2 2E 47
        dec     al                                             ;#333B: FE C8
        cmp     al, [4707h]                                    ;#333D: 3A 06 07 47
        jnb     short 3348h                                    ;#3341: 73 05
        call    near 32E9h                                     ;#3343: E8 A3 FF
        jz      short 334Dh                                    ;#3346: 74 05
        or      byte [472Dh], 80h                              ;#3348: 80 0E 2D 47 80
        mov     al, [bp]                                       ;#334D: 8A 46 00
        call    near 2FF6h                                     ;#3350: E8 A3 FC
        jz      short 3384h                                    ;#3353: 74 2F
        call    near 300Bh                                     ;#3355: E8 B3 FC
        jz      short 3384h                                    ;#3358: 74 2A
        inc     bp                                             ;#335A: 45
        cmp     al, 3Ah                                        ;#335B: 3C 3A
        jz      short 3384h                                    ;#335D: 74 25
        stosb                                                  ;#335F: AA
        and     byte [472Dh], 0EFh                             ;#3360: 80 26 2D 47 EF
        call    near 2FE0h                                     ;#3365: E8 78 FC
        jnz     short 336Fh                                    ;#3368: 75 05
        or      byte [472Dh], 8                                ;#336A: 80 0E 2D 47 08
        call    near 2F6Eh                                     ;#336F: E8 FC FB
        jnz     short 337Dh                                    ;#3372: 75 09
        or      byte [472Dh], 2                                ;#3374: 80 0E 2D 47 02
        mov     [472Fh], di                                    ;#3379: 89 3E 2F 47
        cmp     di, dx                                         ;#337D: 3B FA
        jb      short 334Dh                                    ;#337F: 72 CC
        stc                                                    ;#3381: F9
        jmp     short 338Fh                                    ;#3382: EB 0B
        cmp     [472Fh], di                                    ;#3384: 39 3E 2F 47
        jz      short 338Fh                                    ;#3388: 74 05
        or      byte [472Dh], 4                                ;#338A: 80 0E 2D 47 04
        mov     al, 0                                          ;#338F: B0 00
        stosb                                                  ;#3391: AA
        ret                                                    ;#3392: C3
        xor     dl, dl                                         ;#3393: 32 D2
        mov     al, [cs:4706h]                                 ;#3395: 2E A0 06 47
        add     al, 41h                                        ;#3399: 04 41
        mov     ah, 3Ah                                        ;#339B: B4 3A
        cmp     [si], dl                                       ;#339D: 38 14
        jz      short 33AFh                                    ;#339F: 74 0E
        cmp     [si+1], ah                                     ;#33A1: 38 64 01
        jnz     short 33AFh                                    ;#33A4: 75 09
        lodsw                                                  ;#33A6: AD
        call    near 2F00h                                     ;#33A7: E8 56 FB
        mov     dl, al                                         ;#33AA: 8A D0
        sub     dl, 40h                                        ;#33AC: 80 EA 40
        stosw                                                  ;#33AF: AB
        ret                                                    ;#33B0: C3
        mov     al, [cs:4663h]                                 ;#33B1: 2E A0 63 46
        stosb                                                  ;#33B5: AA
        mov     byte [es:di], 0                                ;#33B6: 26 C6 05 00
        push    ds                                             ;#33BA: 1E
        push    es                                             ;#33BB: 06
        pop     ds                                             ;#33BC: 1F
        mov     si, di                                         ;#33BD: 8B F7
        mov     ah, 47h                                        ;#33BF: B4 47
        int     21h                                            ;#33C1: CD 21
        pop     ds                                             ;#33C3: 1F
        ret                                                    ;#33C4: C3
        mov     al, [si]                                       ;#33C5: 8A 04
        call    near 2F6Eh                                     ;#33C7: E8 A4 FB
        jz      short 33E6h                                    ;#33CA: 74 1A
        push    si                                             ;#33CC: 56
        push    di                                             ;#33CD: 57
        call    near 33B1h                                     ;#33CE: E8 E0 FF
        pop     di                                             ;#33D1: 5F
        pop     si                                             ;#33D2: 5E
        xor     al, al                                         ;#33D3: 32 C0
        mov     cx, 41h                                        ;#33D5: B9 41 00
        repne   scasb                                          ;#33D8: F2 AE
        dec     di                                             ;#33DA: 4F
        mov     al, [cs:4663h]                                 ;#33DB: 2E A0 63 46
        cmp     al, [es:di-1]                                  ;#33DF: 26 3A 45 FF
        jz      short 33E6h                                    ;#33E3: 74 01
        stosb                                                  ;#33E5: AA
        ret                                                    ;#33E6: C3
        call    near 3393h                                     ;#33E7: E8 A9 FF
        call    near 33C5h                                     ;#33EA: E8 D8 FF
        mov     [cs:4731h], di                                 ;#33ED: 2E 89 3E 31 47
        lodsb                                                  ;#33F2: AC
        stosb                                                  ;#33F3: AA
        call    near 2F6Eh                                     ;#33F4: E8 77 FB
        jz      short 33EDh                                    ;#33F7: 74 F4
        or      al, al                                         ;#33F9: 0A C0
        jnz     short 33F2h                                    ;#33FB: 75 F5
        ret                                                    ;#33FD: C3
        call    near 3393h                                     ;#33FE: E8 92 FF
        jmp     short 33EDh                                    ;#3401: EB EA
        stc                                                    ;#3403: F9
        ret                                                    ;#3404: C3
        lds     si, [4736h]                                    ;#3405: C5 36 36 47
        or      si, si                                         ;#3409: 0B F6
        jz      short 3403h                                    ;#340B: 74 F6
        lodsb                                                  ;#340D: AC
        call    near 3004h                                     ;#340E: E8 F3 FB
        jz      short 340Dh                                    ;#3411: 74 FA
        cmp     al, 3Bh                                        ;#3413: 3C 3B
        jz      short 340Dh                                    ;#3415: 74 F6
        or      al, al                                         ;#3417: 0A C0
        jz      short 3403h                                    ;#3419: 74 E8
        dec     si                                             ;#341B: 4E
        mov     di, 478Ah                                      ;#341C: BF 8A 47
        xor     dl, dl                                         ;#341F: 32 D2
        mov     ah, 3Ah                                        ;#3421: B4 3A
        mov     al, [cs:4706h]                                 ;#3423: 2E A0 06 47
        add     al, 41h                                        ;#3427: 04 41
        cmp     [si+1], ah                                     ;#3429: 38 64 01
        jnz     short 343Eh                                    ;#342C: 75 10
        lodsw                                                  ;#342E: AD
        call    near 2F00h                                     ;#342F: E8 CE FA
        mov     dl, al                                         ;#3432: 8A D0
        sub     dl, 40h                                        ;#3434: 80 EA 40
        cmp     dl, [cs:4707h]                                 ;#3437: 2E 3A 16 07 47
        jnbe    short 3482h                                    ;#343C: 77 44
        test    byte [cs:472Dh], 1                             ;#343E: 2E F6 06 2D 47 01
        jz      short 344Bh                                    ;#3444: 74 05
        cmp     [es:di], ax                                    ;#3446: 26 39 05
        jnz     short 348Ch                                    ;#3449: 75 41
        stosw                                                  ;#344B: AB
        call    near 33C5h                                     ;#344C: E8 76 FF
        lodsb                                                  ;#344F: AC
        stosb                                                  ;#3450: AA
        call    near 3004h                                     ;#3451: E8 B0 FB
        jz      short 345Eh                                    ;#3454: 74 08
        cmp     al, 3Bh                                        ;#3456: 3C 3B
        jz      short 345Eh                                    ;#3458: 74 04
        or      al, al                                         ;#345A: 0A C0
        jnz     short 344Fh                                    ;#345C: 75 F1
        dec     si                                             ;#345E: 4E
        dec     di                                             ;#345F: 4F
        push    cs                                             ;#3460: 0E
        pop     ds                                             ;#3461: 1F
        mov     [4736h], si                                    ;#3462: 89 36 36 47
        mov     al, [4663h]                                    ;#3466: A0 63 46
        cmp     al, [di-1]                                     ;#3469: 3A 45 FF
        jz      short 346Fh                                    ;#346C: 74 01
        stosb                                                  ;#346E: AA
        push    di                                             ;#346F: 57
        mov     si, [472Fh]                                    ;#3470: 8B 36 2F 47
        call    near 2FADh                                     ;#3474: E8 36 FB
        pop     si                                             ;#3477: 5E
        call    near 3050h                                     ;#3478: E8 D5 FB
        dec     si                                             ;#347B: 4E
        mov     [4733h], si                                    ;#347C: 89 36 33 47
        clc                                                    ;#3480: F8
        ret                                                    ;#3481: C3
        push    ds                                             ;#3482: 1E
        push    cs                                             ;#3483: 0E
        pop     ds                                             ;#3484: 1F
        mov     dx, 11Bh                                       ;#3485: BA 1B 01
        call    near 39FDh                                     ;#3488: E8 72 05
        pop     ds                                             ;#348B: 1F
        lodsb                                                  ;#348C: AC
        call    near 3004h                                     ;#348D: E8 74 FB
        jz      short 349Ah                                    ;#3490: 74 08
        cmp     al, 3Bh                                        ;#3492: 3C 3B
        jz      short 349Ah                                    ;#3494: 74 04
        or      al, al                                         ;#3496: 0A C0
        jnz     short 348Ch                                    ;#3498: 75 F2
        dec     si                                             ;#349A: 4E
        jmp     near 340Dh                                     ;#349B: E9 6F FF
        mov     ah, 0                                          ;#349E: B4 00
        mov     al, [si]                                       ;#34A0: 8A 04
        call    near 2F18h                                     ;#34A2: E8 73 FA
        jz      short 34C2h                                    ;#34A5: 74 1B
        cmp     byte [si+1], 3Ah                               ;#34A7: 80 7C 01 3A
        jnz     short 34C2h                                    ;#34AB: 75 15
        lodsw                                                  ;#34AD: AD
        call    near 2F00h                                     ;#34AE: E8 4F FA
        sub     al, 40h                                        ;#34B1: 2C 40
        mov     ah, al                                         ;#34B3: 8A E0
        dec     al                                             ;#34B5: FE C8
        cmp     al, [cs:4707h]                                 ;#34B7: 2E 3A 06 07 47
        jb      short 34C0h                                    ;#34BC: 72 02
        mov     ah, 0FFh                                       ;#34BE: B4 FF
        add     al, 41h                                        ;#34C0: 04 41
        or      ah, ah                                         ;#34C2: 0A E4
        ret                                                    ;#34C4: C3
        push    ds                                             ;#34C5: 1E
        push    si                                             ;#34C6: 56
        stc                                                    ;#34C7: F9
        jcxz    34F3h                                          ;#34C8: E3 29
        mov     al, 5Ch                                        ;#34CA: B0 5C
        stosb                                                  ;#34CC: AA
        dec     cx                                             ;#34CD: 49
        push    es                                             ;#34CE: 06
        pop     ds                                             ;#34CF: 1F
        mov     si, di                                         ;#34D0: 8B F7
        mov     byte [si], 0                                   ;#34D2: C6 04 00
        mov     ah, 47h                                        ;#34D5: B4 47
        int     21h                                            ;#34D7: CD 21
        cmc                                                    ;#34D9: F5
        jnb     short 34F3h                                    ;#34DA: 73 17
        cmp     byte [si], 0                                   ;#34DC: 80 3C 00
        jz      short 34F3h                                    ;#34DF: 74 12
        inc     cx                                             ;#34E1: 41
        lodsb                                                  ;#34E2: AC
        call    near 2F00h                                     ;#34E3: E8 1A FA
        call    near 2F60h                                     ;#34E6: E8 77 FA
        stosb                                                  ;#34E9: AA
        or      al, al                                         ;#34EA: 0A C0
        loopne  34E2h                                          ;#34EC: E0 F4
        stc                                                    ;#34EE: F9
        jnz     short 34F3h                                    ;#34EF: 75 02
        dec     di                                             ;#34F1: 4F
        clc                                                    ;#34F2: F8
        pop     si                                             ;#34F3: 5E
        pop     ds                                             ;#34F4: 1F
        ret                                                    ;#34F5: C3
        push    bp                                             ;#34F6: 55
        push    cx                                             ;#34F7: 51
        push    dx                                             ;#34F8: 52
        mov     bp, di                                         ;#34F9: 8B EF
        test    ah, 44h                                        ;#34FB: F6 C4 44
        jz      short 3503h                                    ;#34FE: 74 03
        or      ah, 20h                                        ;#3500: 80 CC 20
        mov     [es:bp+52h], si                                ;#3503: 26 89 76 52
        mov     [es:bp+54h], ds                                ;#3507: 26 8C 5E 54
        mov     [es:bp+51h], ah                                ;#350B: 26 88 66 51
        mov     byte [es:bp+5Bh], 0                            ;#350F: 26 C6 46 5B 00
        mov     byte [es:bp+5Eh], 0                            ;#3514: 26 C6 46 5E 00
        mov     byte [es:bp+50h], 0FFh                         ;#3519: 26 C6 46 50 FF
        mov     word [es:bp+64h], 4Fh                          ;#351E: 26 C7 46 64 4F 00
        xor     bx, bx                                         ;#3524: 33 DB
        call    near 3636h                                     ;#3526: E8 0D 01
        call    near 3673h                                     ;#3529: E8 47 01
        mov     al, [si]                                       ;#352C: 8A 04
        call    near 2F18h                                     ;#352E: E8 E7 F9
        jnb     short 3594h                                    ;#3531: 73 61
        mov     [es:bp+60h], di                                ;#3533: 26 89 7E 60
        mov     [es:bp+62h], di                                ;#3537: 26 89 7E 62
        mov     byte [es:di], 0                                ;#353B: 26 C6 05 00
        mov     [es:bp+5Ch], al                                ;#353F: 26 88 46 5C
        mov     [es:bp+56h], si                                ;#3543: 26 89 76 56
        mov     [es:bp+5Ah], bl                                ;#3547: 26 88 5E 5A
        or      bl, [es:bp+5Bh]                                ;#354B: 26 0A 5E 5B
        and     bl, 7Fh                                        ;#354F: 80 E3 7F
        call    near 36C5h                                     ;#3552: E8 70 01
        call    near 3711h                                     ;#3555: E8 B9 01
        call    near 38BAh                                     ;#3558: E8 5F 03
        mov     [es:bp+5Dh], bh                                ;#355B: 26 88 7E 5D
        mov     [es:bp+5Bh], bl                                ;#355F: 26 88 5E 5B
        mov     bl, [es:bp+5Ah]                                ;#3563: 26 8A 5E 5A
        mov     ah, [es:bp+5Fh]                                ;#3567: 26 8A 66 5F
        mov     al, [es:bp+5Ch]                                ;#356B: 26 8A 46 5C
        mov     si, [es:bp+56h]                                ;#356F: 26 8B 76 56
        cmp     bh, 1                                          ;#3573: 80 FF 01
        cmc                                                    ;#3576: F5
        pop     dx                                             ;#3577: 5A
        pop     cx                                             ;#3578: 59
        pop     bp                                             ;#3579: 5D
        ret                                                    ;#357A: C3
        call    near 39C4h                                     ;#357B: E8 46 04
        test    bl, 48h                                        ;#357E: F6 C3 48
        jnz     short 3588h                                    ;#3581: 75 05
        test    bh, 8                                          ;#3583: F6 C7 08
        jz      short 358Eh                                    ;#3586: 74 06
        and     bh, 0F7h                                       ;#3588: 80 E7 F7
        or      bh, 2                                          ;#358B: 80 CF 02
        and     bl, 83h                                        ;#358E: 80 E3 83
        or      bh, 4                                          ;#3591: 80 CF 04
        mov     [es:bp+60h], di                                ;#3594: 26 89 7E 60
        mov     dh, 4                                          ;#3598: B6 04
        mov     dl, 8                                          ;#359A: B2 08
        mov     cx, 8                                          ;#359C: B9 08 00
        call    near 3997h                                     ;#359F: E8 F5 03
        mov     [es:bp+62h], di                                ;#35A2: 26 89 7E 62
        jnb     short 35AFh                                    ;#35A6: 73 07
        jcxz    35ADh                                          ;#35A8: E3 03
        and     bh, 0FBh                                       ;#35AA: 80 E7 FB
        jmp     short 353Bh                                    ;#35AD: EB 8C
        inc     si                                             ;#35AF: 46
        cmp     al, 5Ch                                        ;#35B0: 3C 5C
        jnz     short 35BDh                                    ;#35B2: 75 09
        jcxz    35B8h                                          ;#35B4: E3 02
        jmp     short 357Bh                                    ;#35B6: EB C3
        or      bh, 2                                          ;#35B8: 80 CF 02
        jmp     short 3594h                                    ;#35BB: EB D7
        cmp     al, 3Ah                                        ;#35BD: 3C 3A
        jnz     short 35D6h                                    ;#35BF: 75 15
        or      bh, 10h                                        ;#35C1: 80 CF 10
        jcxz    35ADh                                          ;#35C4: E3 E7
        and     bh, 0FBh                                       ;#35C6: 80 E7 FB
        test    bl, 8                                          ;#35C9: F6 C3 08
        jnz     short 35ADh                                    ;#35CC: 75 DF
        or      bl, 80h                                        ;#35CE: 80 CB 80
        and     bh, 0EFh                                       ;#35D1: 80 E7 EF
        jmp     short 35ADh                                    ;#35D4: EB D7
        and     bh, 0FBh                                       ;#35D6: 80 E7 FB
        or      bl, 10h                                        ;#35D9: 80 CB 10
        jcxz    35E5h                                          ;#35DC: E3 07
        mov     al, [si]                                       ;#35DE: 8A 04
        call    near 2F18h                                     ;#35E0: E8 35 F9
        jz      short 35EEh                                    ;#35E3: 74 09
        mov     al, 2Eh                                        ;#35E5: B0 2E
        call    near 39C9h                                     ;#35E7: E8 DF 03
        mov     [es:bp+62h], di                                ;#35EA: 26 89 7E 62
        mov     dh, 20h                                        ;#35EE: B6 20
        mov     dl, 40h                                        ;#35F0: B2 40
        mov     cx, 3                                          ;#35F2: B9 03 00
        call    near 3997h                                     ;#35F5: E8 9F 03
        jb      short 3613h                                    ;#35F8: 72 19
        inc     si                                             ;#35FA: 46
        cmp     al, 5Ch                                        ;#35FB: 3C 5C
        jnz     short 360Ch                                    ;#35FD: 75 0D
        jcxz    3609h                                          ;#35FF: E3 08
        test    bl, 4                                          ;#3601: F6 C3 04
        jnz     short 3609h                                    ;#3604: 75 03
        or      bh, 2                                          ;#3606: 80 CF 02
        jmp     near 357Bh                                     ;#3609: E9 6F FF
        cmp     al, 3Ah                                        ;#360C: 3C 3A
        jnz     short 3616h                                    ;#360E: 75 06
        or      bh, 10h                                        ;#3610: 80 CF 10
        jmp     near 353Bh                                     ;#3613: E9 25 FF
        test    bl, 24h                                        ;#3616: F6 C3 24
        jnz     short 3631h                                    ;#3619: 75 16
        and     bl, 0EFh                                       ;#361B: 80 E3 EF
        call    near 39C9h                                     ;#361E: E8 A8 03
        mov     al, [si]                                       ;#3621: 8A 04
        call    near 2F18h                                     ;#3623: E8 F2 F8
        jb      short 3613h                                    ;#3626: 72 EB
        inc     si                                             ;#3628: 46
        cmp     al, 5Ch                                        ;#3629: 3C 5C
        jz      short 3609h                                    ;#362B: 74 DC
        cmp     al, 3Ah                                        ;#362D: 3C 3A
        jz      short 3610h                                    ;#362F: 74 DF
        or      bh, 8                                          ;#3631: 80 CF 08
        jmp     short 3621h                                    ;#3634: EB EB
        call    near 349Eh                                     ;#3636: E8 65 FE
        jz      short 365Bh                                    ;#3639: 74 20
        js      short 3648h                                    ;#363B: 78 0B
        push    ax                                             ;#363D: 50
        mov     al, ah                                         ;#363E: 8A C4
        dec     al                                             ;#3640: FE C8
        call    near 32E9h                                     ;#3642: E8 A4 FC
        pop     ax                                             ;#3645: 58
        jz      short 364Bh                                    ;#3646: 74 03
        or      bh, 1                                          ;#3648: 80 CF 01
        or      bl, 1                                          ;#364B: 80 CB 01
        call    near 39C9h                                     ;#364E: E8 78 03
        mov     al, 3Ah                                        ;#3651: B0 3A
        call    near 39C9h                                     ;#3653: E8 73 03
        mov     [es:bp+5Fh], ah                                ;#3656: 26 88 66 5F
        ret                                                    ;#365A: C3
        test    byte [es:bp+51h], 1                            ;#365B: 26 F6 46 51 01
        jz      short 3656h                                    ;#3660: 74 F4
        or      byte [es:bp+5Bh], 1                            ;#3662: 26 80 4E 5B 01
        mov     al, [cs:4706h]                                 ;#3667: 2E A0 06 47
        inc     al                                             ;#366B: FE C0
        mov     ah, al                                         ;#366D: 8A E0
        add     al, 40h                                        ;#366F: 04 40
        jmp     short 364Eh                                    ;#3671: EB DB
        mov     al, [si]                                       ;#3673: 8A 04
        call    near 2F18h                                     ;#3675: E8 A0 F8
        jb      short 3687h                                    ;#3678: 72 0D
        mov     byte [es:bp+5Eh], 0FFh                         ;#367A: 26 C6 46 5E FF
        cmp     al, 5Ch                                        ;#367F: 3C 5C
        jnz     short 3687h                                    ;#3681: 75 04
        inc     si                                             ;#3683: 46
        jmp     near 39C4h                                     ;#3684: E9 3D 03
        test    byte [es:bp+51h], 2                            ;#3687: 26 F6 46 51 02
        jz      short 36C0h                                    ;#368C: 74 32
        or      byte [es:bp+5Bh], 2                            ;#368E: 26 80 4E 5B 02
        mov     cx, [es:bp+64h]                                ;#3693: 26 8B 4E 64
        mov     dl, [es:bp+5Fh]                                ;#3697: 26 8A 56 5F
        call    near 34C5h                                     ;#369B: E8 27 FE
        mov     [es:bp+64h], cx                                ;#369E: 26 89 4E 64
        jb      short 36C1h                                    ;#36A2: 72 1D
        cmp     byte [es:bp+50h], 0FFh                         ;#36A4: 26 80 7E 50 FF
        jnz     short 36C1h                                    ;#36A9: 75 16
        cmp     byte [es:di-1], 5Ch                            ;#36AB: 26 80 7D FF 5C
        jz      short 36C0h                                    ;#36B0: 74 0E
        mov     al, [si]                                       ;#36B2: 8A 04
        call    near 2F18h                                     ;#36B4: E8 61 F8
        jb      short 36C0h                                    ;#36B7: 72 07
        cmp     al, 3Ah                                        ;#36B9: 3C 3A
        jz      short 36C0h                                    ;#36BB: 74 03
        call    near 39C7h                                     ;#36BD: E8 07 03
        ret                                                    ;#36C0: C3
        int     0                                              ;#36C1: CD 00
        jmp     short 36C3h                                    ;#36C3: EB FE
        test    byte [es:bp+51h], 4                            ;#36C5: 26 F6 46 51 04
        jnz     short 36DAh                                    ;#36CA: 75 0E
        test    bl, 4                                          ;#36CC: F6 C3 04
        jnz     short 36D9h                                    ;#36CF: 75 08
        test    bl, 20h                                        ;#36D1: F6 C3 20
        jz      short 36D9h                                    ;#36D4: 74 03
        or      bh, 8                                          ;#36D6: 80 CF 08
        ret                                                    ;#36D9: C3
        test    bh, 80h                                        ;#36DA: F6 C7 80
        jnz     short 36D9h                                    ;#36DD: 75 FA
        mov     ax, [es:bp+60h]                                ;#36DF: 26 8B 46 60
        cmp     ax, [es:bp+62h]                                ;#36E3: 26 3B 46 62
        jnz     short 36F4h                                    ;#36E7: 75 0B
        call    near 3984h                                     ;#36E9: E8 98 02
        jz      short 36F1h                                    ;#36EC: 74 03
        jmp     near 3840h                                     ;#36EE: E9 4F 01
        jmp     near 3843h                                     ;#36F1: E9 4F 01
        test    bl, 34h                                        ;#36F4: F6 C3 34
        jz      short 36EEh                                    ;#36F7: 74 F5
        test    bl, 4                                          ;#36F9: F6 C3 04
        jnz     short 3709h                                    ;#36FC: 75 0B
        call    near 3893h                                     ;#36FE: E8 92 01
        test    bl, 20h                                        ;#3701: F6 C3 20
        jnz     short 3709h                                    ;#3704: 75 03
        jmp     near 387Dh                                     ;#3706: E9 74 01
        test    bl, 8                                          ;#3709: F6 C3 08
        jz      short 36D9h                                    ;#370C: 74 CB
        jmp     near 385Ch                                     ;#370E: E9 4B 01
        test    byte [es:bp+51h], 20h                          ;#3711: 26 F6 46 51 20
        jnz     short 3719h                                    ;#3716: 75 01
        ret                                                    ;#3718: C3
        push    ds                                             ;#3719: 1E
        push    dx                                             ;#371A: 52
        push    ax                                             ;#371B: 50
        push    es                                             ;#371C: 06
        pop     ds                                             ;#371D: 1F
        lea     dx, [bp+66h]                                   ;#371E: 8D 56 66
        mov     ah, 1Ah                                        ;#3721: B4 1A
        int     21h                                            ;#3723: CD 21
        pop     ax                                             ;#3725: 58
        pop     dx                                             ;#3726: 5A
        pop     ds                                             ;#3727: 1F
        test    bh, 83h                                        ;#3728: F6 C7 83
        jnz     short 3792h                                    ;#372B: 75 65
        test    bh, 0Ch                                        ;#372D: F6 C7 0C
        jnz     short 377Fh                                    ;#3730: 75 4D
        test    bl, 48h                                        ;#3732: F6 C3 48
        jnz     short 377Fh                                    ;#3735: 75 48
        push    di                                             ;#3737: 57
        call    near 37DDh                                     ;#3738: E8 A2 00
        pop     di                                             ;#373B: 5F
        jb      short 375Ah                                    ;#373C: 72 1C
        jnz     short 3796h                                    ;#373E: 75 56
        test    cl, 10h                                        ;#3740: F6 C1 10
        jz      short 374Fh                                    ;#3743: 74 0A
        test    byte [es:bp+51h], 4                            ;#3745: 26 F6 46 51 04
        jz      short 3770h                                    ;#374A: 74 24
        jmp     near 3840h                                     ;#374C: E9 F1 00
        test    byte [es:bp+51h], 4                            ;#374F: 26 F6 46 51 04
        jz      short 3759h                                    ;#3754: 74 03
        call    near 385Ch                                     ;#3756: E8 03 01
        ret                                                    ;#3759: C3
        test    byte [es:bp+51h], 4                            ;#375A: 26 F6 46 51 04
        jnz     short 377Ch                                    ;#375F: 75 1B
        push    di                                             ;#3761: 57
        mov     di, [es:bp+60h]                                ;#3762: 26 8B 7E 60
        cmp     byte [es:di], 2Eh                              ;#3766: 26 80 3D 2E
        pop     di                                             ;#376A: 5F
        jnz     short 377Fh                                    ;#376B: 75 12
        or      bh, 40h                                        ;#376D: 80 CF 40
        and     bl, 0CBh                                       ;#3770: 80 E3 CB
        mov     [es:bp+60h], di                                ;#3773: 26 89 7E 60
        mov     [es:bp+62h], di                                ;#3777: 26 89 7E 62
        ret                                                    ;#377B: C3
        call    near 385Ch                                     ;#377C: E8 DD 00
        push    di                                             ;#377F: 57
        mov     di, [es:bp+60h]                                ;#3780: 26 8B 7E 60
        call    near 380Fh                                     ;#3784: E8 88 00
        pop     di                                             ;#3787: 5F
        jb      short 3792h                                    ;#3788: 72 08
        jnz     short 3792h                                    ;#378A: 75 06
        test    cl, 10h                                        ;#378C: F6 C1 10
        jz      short 3792h                                    ;#378F: 74 01
        ret                                                    ;#3791: C3
        or      bh, 40h                                        ;#3792: 80 CF 40
        ret                                                    ;#3795: C3
        test    byte [es:bp+51h], 10h                          ;#3796: 26 F6 46 51 10
        jnz     short 37D9h                                    ;#379B: 75 3C
        mov     si, bp                                         ;#379D: 8B F5
        mov     di, bp                                         ;#379F: 8B FD
        cmp     si, [es:bp+60h]                                ;#37A1: 26 3B 76 60
        jz      short 37AEh                                    ;#37A5: 74 07
        inc     si                                             ;#37A7: 46
        inc     word [es:bp+64h]                               ;#37A8: 26 FF 46 64
        jmp     short 37A1h                                    ;#37AC: EB F3
        lodsb                                                  ;#37AE: 26 AC
        stosb                                                  ;#37B0: AA
        or      al, al                                         ;#37B1: 0A C0
        jz      short 37C8h                                    ;#37B3: 74 13
        cmp     al, 2Eh                                        ;#37B5: 3C 2E
        jnz     short 37AEh                                    ;#37B7: 75 F5
        mov     byte [es:di-1], 0                              ;#37B9: 26 C6 45 FF 00
        inc     word [es:bp+64h]                               ;#37BE: 26 FF 46 64
        lodsb                                                  ;#37C2: 26 AC
        or      al, al                                         ;#37C4: 0A C0
        jnz     short 37BEh                                    ;#37C6: 75 F6
        dec     di                                             ;#37C8: 4F
        mov     [es:bp+60h], bp                                ;#37C9: 26 89 6E 60
        mov     [es:bp+62h], di                                ;#37CD: 26 89 7E 62
        mov     byte [es:bp+5Fh], 0                            ;#37D1: 26 C6 46 5F 00
        and     bl, 8Ch                                        ;#37D6: 80 E3 8C
        or      bl, 80h                                        ;#37D9: 80 CB 80
        ret                                                    ;#37DC: C3
        call    near 3962h                                     ;#37DD: E8 82 01
        jnb     short 37E8h                                    ;#37E0: 73 06
        mov     cx, 10h                                        ;#37E2: B9 10 00
        xor     al, al                                         ;#37E5: 32 C0
        ret                                                    ;#37E7: C3
        push    ax                                             ;#37E8: 50
        push    dx                                             ;#37E9: 52
        push    ds                                             ;#37EA: 1E
        push    es                                             ;#37EB: 06
        pop     ds                                             ;#37EC: 1F
        mov     dx, bp                                         ;#37ED: 8B D5
        mov     cx, 16h                                        ;#37EF: B9 16 00
        mov     ah, 4Eh                                        ;#37F2: B4 4E
        int     21h                                            ;#37F4: CD 21
        jb      short 380Bh                                    ;#37F6: 72 13
        mov     ch, 0                                          ;#37F8: B5 00
        mov     cl, [ds:bp+7Bh]                                ;#37FA: 3E 8A 4E 7B
        mov     ax, [ds:bp+73h]                                ;#37FE: 3E 8B 46 73
        cmp     ax, 0FFFFh                                     ;#3802: 3D FF FF
        jz      short 3809h                                    ;#3805: 74 02
        xor     ax, ax                                         ;#3807: 33 C0
        or      ax, ax                                         ;#3809: 0B C0
        pop     ds                                             ;#380B: 1F
        pop     dx                                             ;#380C: 5A
        pop     ax                                             ;#380D: 58
        ret                                                    ;#380E: C3
        call    near 3962h                                     ;#380F: E8 50 01
        jnb     short 381Ah                                    ;#3812: 73 06
        mov     cx, 10h                                        ;#3814: B9 10 00
        xor     al, al                                         ;#3817: 32 C0
        ret                                                    ;#3819: C3
        push    ax                                             ;#381A: 50
        push    dx                                             ;#381B: 52
        push    ds                                             ;#381C: 1E
        push    es                                             ;#381D: 06
        pop     ds                                             ;#381E: 1F
        mov     dx, bp                                         ;#381F: 8B D5
        mov     cx, 16h                                        ;#3821: B9 16 00
        mov     ah, 4Eh                                        ;#3824: B4 4E
        int     21h                                            ;#3826: CD 21
        jnb     short 3837h                                    ;#3828: 73 0D
        cmp     ax, 2                                          ;#382A: 3D 02 00
        jz      short 3837h                                    ;#382D: 74 08
        cmp     ax, 12h                                        ;#382F: 3D 12 00
        jz      short 3837h                                    ;#3832: 74 03
        stc                                                    ;#3834: F9
        jmp     short 383Ch                                    ;#3835: EB 05
        mov     cx, 10h                                        ;#3837: B9 10 00
        xor     ax, ax                                         ;#383A: 33 C0
        pop     ds                                             ;#383C: 1F
        pop     dx                                             ;#383D: 5A
        pop     ax                                             ;#383E: 58
        ret                                                    ;#383F: C3
        call    near 39C4h                                     ;#3840: E8 81 01
        test    bh, 8                                          ;#3843: F6 C7 08
        jz      short 384Eh                                    ;#3846: 74 06
        and     bh, 0F7h                                       ;#3848: 80 E7 F7
        or      bh, 2                                          ;#384B: 80 CF 02
        mov     [es:bp+60h], di                                ;#384E: 26 89 7E 60
        or      bl, 0Ch                                        ;#3852: 80 CB 0C
        mov     al, 2Ah                                        ;#3855: B0 2A
        call    near 39C9h                                     ;#3857: E8 6F 01
        jmp     short 387Dh                                    ;#385A: EB 21
        test    bl, 20h                                        ;#385C: F6 C3 20
        jnz     short 3877h                                    ;#385F: 75 16
        test    byte [es:bp+51h], 8                            ;#3861: 26 F6 46 51 08
        jz      short 3877h                                    ;#3866: 74 0F
        test    byte [es:bp+51h], 80h                          ;#3868: 26 F6 46 51 80
        jz      short 3878h                                    ;#386D: 74 09
        test    bl, 10h                                        ;#386F: F6 C3 10
        jz      short 387Dh                                    ;#3872: 74 09
        and     bl, 0EFh                                       ;#3874: 80 E3 EF
        ret                                                    ;#3877: C3
        test    bl, 10h                                        ;#3878: F6 C3 10
        jz      short 3877h                                    ;#387B: 74 FA
        or      bl, 70h                                        ;#387D: 80 CB 70
        mov     al, 2Eh                                        ;#3880: B0 2E
        call    near 39C9h                                     ;#3882: E8 44 01
        mov     [es:bp+62h], di                                ;#3885: 26 89 7E 62
        mov     al, 2Ah                                        ;#3889: B0 2A
        call    near 39C9h                                     ;#388B: E8 3B 01
        mov     byte [es:di], 0                                ;#388E: 26 C6 05 00
        ret                                                    ;#3892: C3
        or      bl, 0Ch                                        ;#3893: 80 CB 0C
        mov     di, [es:bp+60h]                                ;#3896: 26 8B 7E 60
        mov     al, 2Ah                                        ;#389A: B0 2A
        stosb                                                  ;#389C: AA
        test    bl, 20h                                        ;#389D: F6 C3 20
        jz      short 38B5h                                    ;#38A0: 74 13
        mov     al, 2Eh                                        ;#38A2: B0 2E
        inc     word [es:bp+62h]                               ;#38A4: 26 FF 46 62
        xchg    [es:di], al                                    ;#38A8: 26 86 05
        inc     di                                             ;#38AB: 47
        cmp     byte [es:di], 0                                ;#38AC: 26 80 3D 00
        jnz     short 38A8h                                    ;#38B0: 75 F6
        call    near 39C9h                                     ;#38B2: E8 14 01
        mov     byte [es:di], 0                                ;#38B5: 26 C6 05 00
        ret                                                    ;#38B9: C3
        test    bl, 4                                          ;#38BA: F6 C3 04
        jz      short 38C7h                                    ;#38BD: 74 08
        test    bl, 20h                                        ;#38BF: F6 C3 20
        jnz     short 38C7h                                    ;#38C2: 75 03
        and     bl, 0EFh                                       ;#38C4: 80 E3 EF
        mov     [es:bp+58h], di                                ;#38C7: 26 89 7E 58
        test    byte [es:bp+51h], 40h                          ;#38CB: 26 F6 46 51 40
        jz      short 38D7h                                    ;#38D0: 74 05
        test    bh, 40h                                        ;#38D2: F6 C7 40
        jz      short 38E3h                                    ;#38D5: 74 0C
        push    di                                             ;#38D7: 57
        inc     di                                             ;#38D8: 47
        mov     cx, [es:bp+64h]                                ;#38D9: 26 8B 4E 64
        xor     al, al                                         ;#38DD: 32 C0
        rep     stosb                                          ;#38DF: F3 AA
        pop     di                                             ;#38E1: 5F
        ret                                                    ;#38E2: C3
        mov     di, [es:bp+60h]                                ;#38E3: 26 8B 7E 60
        xor     cx, cx                                         ;#38E7: 33 C9
        xor     dx, dx                                         ;#38E9: 33 D2
        mov     si, di                                         ;#38EB: 8B F7
        call    near 3962h                                     ;#38ED: E8 72 00
        jb      short 3920h                                    ;#38F0: 72 2E
        dec     di                                             ;#38F2: 4F
        call    near 3984h                                     ;#38F3: E8 8E 00
        jnz     short 38F2h                                    ;#38F6: 75 FA
        cmp     byte [es:di], 2Eh                              ;#38F8: 26 80 3D 2E
        jnz     short 3909h                                    ;#38FC: 75 0B
        add     si, dx                                         ;#38FE: 03 F2
        push    si                                             ;#3900: 56
        inc     cx                                             ;#3901: 41
        cmp     byte [es:di+1], 2Eh                            ;#3902: 26 80 7D 01 2E
        jz      short 38EBh                                    ;#3907: 74 E2
        jcxz    38EBh                                          ;#3909: E3 E0
        dec     cx                                             ;#390B: 49
        pop     si                                             ;#390C: 5E
        sub     si, dx                                         ;#390D: 2B F2
        mov     ax, si                                         ;#390F: 8B C6
        sub     ax, di                                         ;#3911: 2B C7
        add     dx, ax                                         ;#3913: 03 D0
        push    di                                             ;#3915: 57
        lodsb                                                  ;#3916: 26 AC
        stosb                                                  ;#3918: AA
        or      al, al                                         ;#3919: 0A C0
        jnz     short 3916h                                    ;#391B: 75 F9
        pop     di                                             ;#391D: 5F
        jmp     short 38EBh                                    ;#391E: EB CB
        shl     cx, 1                                          ;#3920: D1 E1
        add     sp, cx                                         ;#3922: 03 E1
        sub     [es:bp+60h], dx                                ;#3924: 26 29 56 60
        sub     [es:bp+62h], dx                                ;#3928: 26 29 56 62
        add     [es:bp+64h], dx                                ;#392C: 26 01 56 64
        sub     [es:bp+58h], dx                                ;#3930: 26 29 56 58
        mov     di, [es:bp+58h]                                ;#3934: 26 8B 7E 58
        test    bh, 4                                          ;#3938: F6 C7 04
        jnz     short 395Fh                                    ;#393B: 75 22
        push    di                                             ;#393D: 57
        call    near 3962h                                     ;#393E: E8 21 00
        pop     di                                             ;#3941: 5F
        jb      short 395Fh                                    ;#3942: 72 1B
        cmp     byte [di-1], 5Ch                               ;#3944: 80 7D FF 5C
        jnz     short 395Fh                                    ;#3948: 75 15
        dec     di                                             ;#394A: 4F
        mov     byte [es:di], 0                                ;#394B: 26 C6 05 00
        mov     [es:bp+58h], di                                ;#394F: 26 89 7E 58
        dec     word [es:bp+60h]                               ;#3953: 26 FF 4E 60
        dec     word [es:bp+62h]                               ;#3957: 26 FF 4E 62
        inc     word [es:bp+64h]                               ;#395B: 26 FF 46 64
        jmp     near 38D7h                                     ;#395F: E9 75 FF
        cmp     di, bp                                         ;#3962: 3B FD
        jz      short 3982h                                    ;#3964: 74 1C
        cmp     byte [es:di-1], 3Ah                            ;#3966: 26 80 7D FF 3A
        jz      short 3982h                                    ;#396B: 74 15
        cmp     byte [es:di-1], 5Ch                            ;#396D: 26 80 7D FF 5C
        jnz     short 3980h                                    ;#3972: 75 0C
        dec     di                                             ;#3974: 4F
        cmp     di, bp                                         ;#3975: 3B FD
        jz      short 3982h                                    ;#3977: 74 09
        cmp     byte [es:di-1], 3Ah                            ;#3979: 26 80 7D FF 3A
        jz      short 3982h                                    ;#397E: 74 02
        clc                                                    ;#3980: F8
        ret                                                    ;#3981: C3
        stc                                                    ;#3982: F9
        ret                                                    ;#3983: C3
        cmp     di, bp                                         ;#3984: 3B FD
        stc                                                    ;#3986: F9
        jz      short 3996h                                    ;#3987: 74 0D
        cmp     byte [es:di-1], 3Ah                            ;#3989: 26 80 7D FF 3A
        stc                                                    ;#398E: F9
        jz      short 3996h                                    ;#398F: 74 05
        cmp     byte [es:di-1], 5Ch                            ;#3991: 26 80 7D FF 5C
        ret                                                    ;#3996: C3
        lodsb                                                  ;#3997: AC
        call    near 2F18h                                     ;#3998: E8 7D F5
        jz      short 39B9h                                    ;#399B: 74 1C
        or      bl, dh                                         ;#399D: 0A DE
        cmp     al, 3Fh                                        ;#399F: 3C 3F
        jz      short 39ACh                                    ;#39A1: 74 09
        cmp     al, 2Ah                                        ;#39A3: 3C 2A
        jnz     short 39AEh                                    ;#39A5: 75 07
        jcxz    39ACh                                          ;#39A7: E3 03
        mov     cx, 1                                          ;#39A9: B9 01 00
        or      bl, dl                                         ;#39AC: 0A DA
        jcxz    3997h                                          ;#39AE: E3 E7
        call    near 2F00h                                     ;#39B0: E8 4D F5
        call    near 39C9h                                     ;#39B3: E8 13 00
        dec     cx                                             ;#39B6: 49
        jmp     short 3997h                                    ;#39B7: EB DE
        pushf                                                  ;#39B9: 9C
        dec     si                                             ;#39BA: 4E
        xor     cx, cx                                         ;#39BB: 33 C9
        test    dh, bl                                         ;#39BD: 84 DE
        jz      short 39C2h                                    ;#39BF: 74 01
        inc     cx                                             ;#39C1: 41
        popf                                                   ;#39C2: 9D
        ret                                                    ;#39C3: C3
        or      bl, 2                                          ;#39C4: 80 CB 02
        mov     al, 5Ch                                        ;#39C7: B0 5C
        cmp     word [es:bp+64h], 0                            ;#39C9: 26 83 7E 64 00
        jz      short 39D6h                                    ;#39CE: 74 06
        stosb                                                  ;#39D0: AA
        dec     word [es:bp+64h]                               ;#39D1: 26 FF 4E 64
        ret                                                    ;#39D5: C3
        or      bh, 80h                                        ;#39D6: 80 CF 80
        ret                                                    ;#39D9: C3
        push    ax                                             ;#39DA: 50
        mov     al, 0                                          ;#39DB: B0 00
        push    bx                                             ;#39DD: 53
        mov     bx, 1                                          ;#39DE: BB 01 00
        clc                                                    ;#39E1: F8
        jmp     short 3A05h                                    ;#39E2: EB 21
        push    ax                                             ;#39E4: 50
        mov     al, 0                                          ;#39E5: B0 00
        jmp     short 39F1h                                    ;#39E7: EB 08
        push    ax                                             ;#39E9: 50
        mov     al, 0Dh                                        ;#39EA: B0 0D
        jmp     short 39F1h                                    ;#39EC: EB 03
        push    ax                                             ;#39EE: 50
        mov     al, 24h                                        ;#39EF: B0 24
        push    bx                                             ;#39F1: 53
        mov     bx, 1                                          ;#39F2: BB 01 00
        stc                                                    ;#39F5: F9
        jmp     short 3A05h                                    ;#39F6: EB 0D
        push    ax                                             ;#39F8: 50
        mov     al, 0                                          ;#39F9: B0 00
        jmp     short 3A00h                                    ;#39FB: EB 03
        push    ax                                             ;#39FD: 50
        mov     al, 24h                                        ;#39FE: B0 24
        push    bx                                             ;#3A00: 53
        mov     bx, 2                                          ;#3A01: BB 02 00
        stc                                                    ;#3A04: F9
        push    cx                                             ;#3A05: 51
        push    dx                                             ;#3A06: 52
        push    es                                             ;#3A07: 06
        push    di                                             ;#3A08: 57
        pushf                                                  ;#3A09: 9C
        push    ds                                             ;#3A0A: 1E
        pop     es                                             ;#3A0B: 07
        mov     di, dx                                         ;#3A0C: 8B FA
        mov     cx, 0FFFFh                                     ;#3A0E: B9 FF FF
        repne   scasb                                          ;#3A11: F2 AE
        neg     cx                                             ;#3A13: F7 D9
        sub     cx, 2                                          ;#3A15: 83 E9 02
        popf                                                   ;#3A18: 9D
        jnb     short 3A2Fh                                    ;#3A19: 73 14
        mov     ax, 180Dh                                      ;#3A1B: B8 0D 18
        int     21h                                            ;#3A1E: CD 21
        mov     ah, 40h                                        ;#3A20: B4 40
        int     21h                                            ;#3A22: CD 21
        pushf                                                  ;#3A24: 9C
        push    ax                                             ;#3A25: 50
        mov     ax, 180Eh                                      ;#3A26: B8 0E 18
        int     21h                                            ;#3A29: CD 21
        pop     ax                                             ;#3A2B: 58
        popf                                                   ;#3A2C: 9D
        jmp     short 3A33h                                    ;#3A2D: EB 04
        mov     ah, 40h                                        ;#3A2F: B4 40
        int     21h                                            ;#3A31: CD 21
        jb      short 3A40h                                    ;#3A33: 72 0B
        cmp     cx, ax                                         ;#3A35: 3B C8
        jnz     short 3A42h                                    ;#3A37: 75 09
        pop     di                                             ;#3A39: 5F
        pop     es                                             ;#3A3A: 07
        pop     dx                                             ;#3A3B: 5A
        pop     cx                                             ;#3A3C: 59
        pop     bx                                             ;#3A3D: 5B
        pop     ax                                             ;#3A3E: 58
        ret                                                    ;#3A3F: C3
        xor     ax, ax                                         ;#3A40: 33 C0
        inc     ax                                             ;#3A42: 40
        cmp     cx, ax                                         ;#3A43: 3B C8
        lahf                                                   ;#3A45: 9F
        push    ax                                             ;#3A46: 50
        mov     ax, 4400h                                      ;#3A47: B8 00 44
        int     21h                                            ;#3A4A: CD 21
        pop     ax                                             ;#3A4C: 58
        test    dl, 80h                                        ;#3A4D: F6 C2 80
        jz      short 3A5Ah                                    ;#3A50: 74 08
        sahf                                                   ;#3A52: 9E
        jz      short 3A39h                                    ;#3A53: 74 E4
        mov     dx, 0AA3h                                      ;#3A55: BA A3 0A
        jmp     short 3A6Eh                                    ;#3A58: EB 14
        push    ds                                             ;#3A5A: 1E
        mov     ds, [cs:4660h]                                 ;#3A5B: 2E 8E 1E 60 46
        test    byte [339h], 2                                 ;#3A60: F6 06 39 03 02
        pop     ds                                             ;#3A65: 1F
        mov     dx, 2E9h                                       ;#3A66: BA E9 02
        jnz     short 3A6Eh                                    ;#3A69: 75 03
        mov     dx, 0A8Dh                                      ;#3A6B: BA 8D 0A
        push    ds                                             ;#3A6E: 1E
        mov     ds, [cs:4660h]                                 ;#3A6F: 2E 8E 1E 60 46
        and     byte [339h], 0FCh                              ;#3A74: 80 26 39 03 FC
        or      byte [336h], 3                                 ;#3A79: 80 0E 36 03 03
        pop     ds                                             ;#3A7E: 1F
        cmp     bx, 2                                          ;#3A7F: 83 FB 02
        jz      short 3A39h                                    ;#3A82: 74 B5
        jmp     near 2EE9h                                     ;#3A84: E9 62 F4
        push    ds                                             ;#3A87: 1E
        push    es                                             ;#3A88: 06
        call    near 3AD6h                                     ;#3A89: E8 4A 00
        push    cs                                             ;#3A8C: 0E
        pop     ds                                             ;#3A8D: 1F
        mov     si, 522h                                       ;#3A8E: BE 22 05
        mov     cx, 7                                          ;#3A91: B9 07 00
        call    near 311Ch                                     ;#3A94: E8 85 F6
        pushf                                                  ;#3A97: 9C
        add     di, cx                                         ;#3A98: 03 F9
        popf                                                   ;#3A9A: 9D
        push    es                                             ;#3A9B: 06
        pop     ds                                             ;#3A9C: 1F
        mov     si, di                                         ;#3A9D: 8B F7
        push    cs                                             ;#3A9F: 0E
        pop     es                                             ;#3AA0: 07
        jnb     short 3AB1h                                    ;#3AA1: 73 0E
        call    near 3AE3h                                     ;#3AA3: E8 3D 00
        mov     al, [cs:529h]                                  ;#3AA6: 2E A0 29 05
        call    near 3AE9h                                     ;#3AAA: E8 3C 00
        pop     es                                             ;#3AAD: 07
        pop     ds                                             ;#3AAE: 1F
        ret                                                    ;#3AAF: C3
        inc     si                                             ;#3AB0: 46
        lodsb                                                  ;#3AB1: AC
        or      al, al                                         ;#3AB2: 0A C0
        jz      short 3AADh                                    ;#3AB4: 74 F7
        cmp     al, 24h                                        ;#3AB6: 3C 24
        jz      short 3ABFh                                    ;#3AB8: 74 05
        call    near 3AE9h                                     ;#3ABA: E8 2C 00
        jmp     short 3AB1h                                    ;#3ABD: EB F2
        cmp     byte [si], 0                                   ;#3ABF: 80 3C 00
        jz      short 3AADh                                    ;#3AC2: 74 E9
        mov     di, 0BF8h                                      ;#3AC4: BF F8 0B
        call    near 3140h                                     ;#3AC7: E8 76 F6
        jcxz    3AB0h                                          ;#3ACA: E3 E4
        push    ds                                             ;#3ACC: 1E
        push    si                                             ;#3ACD: 56
        push    cs                                             ;#3ACE: 0E
        pop     ds                                             ;#3ACF: 1F
        call    cx                                             ;#3AD0: FF D1
        pop     si                                             ;#3AD2: 5E
        pop     ds                                             ;#3AD3: 1F
        jmp     short 3AB1h                                    ;#3AD4: EB DB
        push    ds                                             ;#3AD6: 1E
        push    dx                                             ;#3AD7: 52
        push    cs                                             ;#3AD8: 0E
        pop     ds                                             ;#3AD9: 1F
        mov     dx, 52Eh                                       ;#3ADA: BA 2E 05
        call    near 39EEh                                     ;#3ADD: E8 0E FF
        pop     dx                                             ;#3AE0: 5A
        pop     ds                                             ;#3AE1: 1F
        ret                                                    ;#3AE2: C3
        mov     al, [cs:4706h]                                 ;#3AE3: 2E A0 06 47
        add     al, 41h                                        ;#3AE7: 04 41
        push    ax                                             ;#3AE9: 50
        push    dx                                             ;#3AEA: 52
        mov     dl, al                                         ;#3AEB: 8A D0
        mov     ax, 180Dh                                      ;#3AED: B8 0D 18
        int     21h                                            ;#3AF0: CD 21
        mov     ah, 2                                          ;#3AF2: B4 02
        int     21h                                            ;#3AF4: CD 21
        mov     ax, 180Eh                                      ;#3AF6: B8 0E 18
        int     21h                                            ;#3AF9: CD 21
        pop     dx                                             ;#3AFB: 5A
        pop     ax                                             ;#3AFC: 58
        ret                                                    ;#3AFD: C3
        push    ax                                             ;#3AFE: 50
        mov     al, 20h                                        ;#3AFF: B0 20
        call    near 3AE9h                                     ;#3B01: E8 E5 FF
        call    near 3AE9h                                     ;#3B04: E8 E2 FF
        pop     ax                                             ;#3B07: 58
        ret                                                    ;#3B08: C3
        add     al, 41h                                        ;#3B09: 04 41
        call    near 3AE9h                                     ;#3B0B: E8 DB FF
        mov     al, 3Ah                                        ;#3B0E: B0 3A
        jmp     short 3AE9h                                    ;#3B10: EB D7
        push    ds                                             ;#3B12: 1E
        push    dx                                             ;#3B13: 52
        push    cs                                             ;#3B14: 0E
        pop     ds                                             ;#3B15: 1F
        mov     dx, 1E0h                                       ;#3B16: BA E0 01
        call    near 39E4h                                     ;#3B19: E8 C8 FE
        pop     dx                                             ;#3B1C: 5A
        pop     ds                                             ;#3B1D: 1F
        ret                                                    ;#3B1E: C3
        mov     al, 24h                                        ;#3B1F: B0 24
        jmp     short 3AE9h                                    ;#3B21: EB C6
        mov     al, 1Bh                                        ;#3B23: B0 1B
        jmp     short 3AE9h                                    ;#3B25: EB C2
        mov     al, 3Ch                                        ;#3B27: B0 3C
        jmp     short 3AE9h                                    ;#3B29: EB BE
        mov     al, 3Dh                                        ;#3B2B: B0 3D
        jmp     short 3AE9h                                    ;#3B2D: EB BA
        mov     al, 3Eh                                        ;#3B2F: B0 3E
        jmp     short 3AE9h                                    ;#3B31: EB B6
        mov     al, 7Ch                                        ;#3B33: B0 7C
        jmp     short 3AE9h                                    ;#3B35: EB B2
        mov     dx, 52Ah                                       ;#3B37: BA 2A 05
        jmp     near 39EEh                                     ;#3B3A: E9 B1 FE
        mov     si, 47DAh                                      ;#3B3D: BE DA 47
        mov     byte [si], 0                                   ;#3B40: C6 04 00
        mov     di, 47DAh                                      ;#3B43: BF DA 47
        call    near 3393h                                     ;#3B46: E8 4A F8
        call    near 33B1h                                     ;#3B49: E8 65 F8
        mov     dx, 47DAh                                      ;#3B4C: BA DA 47
        jmp     near 39E4h                                     ;#3B4F: E9 92 FE
        mov     ds, [4660h]                                    ;#3B52: 8E 1E 60 46
        mov     dx, 0B28h                                      ;#3B56: BA 28 0B
        jmp     near 39EEh                                     ;#3B59: E9 92 FE
        mov     ah, 2Ah                                        ;#3B5C: B4 2A
        int     21h                                            ;#3B5E: CD 21
        mov     di, 470Bh                                      ;#3B60: BF 0B 47
        mov     si, 66Ch                                       ;#3B63: BE 6C 06
        call    near 3260h                                     ;#3B66: E8 F7 F6
        mov     al, 20h                                        ;#3B69: B0 20
        stosb                                                  ;#3B6B: AA
        mov     bh, 10h                                        ;#3B6C: B7 10
        mov     al, dl                                         ;#3B6E: 8A C2
        call    near 326Ah                                     ;#3B70: E8 F7 F6
        mov     al, 2Dh                                        ;#3B73: B0 2D
        stosb                                                  ;#3B75: AA
        mov     al, dh                                         ;#3B76: 8A C6
        dec     al                                             ;#3B78: FE C8
        mov     si, 648h                                       ;#3B7A: BE 48 06
        call    near 3260h                                     ;#3B7D: E8 E0 F6
        mov     al, 2Dh                                        ;#3B80: B0 2D
        stosb                                                  ;#3B82: AA
        xchg    ax, cx                                         ;#3B83: 91
        mov     dl, 64h                                        ;#3B84: B2 64
        div     dl                                             ;#3B86: F6 F2
        push    ax                                             ;#3B88: 50
        call    near 326Ah                                     ;#3B89: E8 DE F6
        pop     ax                                             ;#3B8C: 58
        xchg    ah, al                                         ;#3B8D: 86 C4
        call    near 326Ah                                     ;#3B8F: E8 D8 F6
        xor     al, al                                         ;#3B92: 32 C0
        stosb                                                  ;#3B94: AA
        mov     dx, 470Bh                                      ;#3B95: BA 0B 47
        jmp     near 39E4h                                     ;#3B98: E9 49 FE
        mov     ah, 2Ch                                        ;#3B9B: B4 2C
        int     21h                                            ;#3B9D: CD 21
        mov     di, 470Bh                                      ;#3B9F: BF 0B 47
        mov     bh, 10h                                        ;#3BA2: B7 10
        mov     al, ch                                         ;#3BA4: 8A C5
        call    near 326Ah                                     ;#3BA6: E8 C1 F6
        mov     al, 3Ah                                        ;#3BA9: B0 3A
        stosb                                                  ;#3BAB: AA
        mov     al, cl                                         ;#3BAC: 8A C1
        call    near 326Ah                                     ;#3BAE: E8 B9 F6
        mov     al, 3Ah                                        ;#3BB1: B0 3A
        stosb                                                  ;#3BB3: AA
        mov     al, dh                                         ;#3BB4: 8A C6
        call    near 326Ah                                     ;#3BB6: E8 B1 F6
        mov     al, 2Eh                                        ;#3BB9: B0 2E
        stosb                                                  ;#3BBB: AA
        mov     al, dl                                         ;#3BBC: 8A C2
        call    near 326Ah                                     ;#3BBE: E8 A9 F6
        jmp     short 3B92h                                    ;#3BC1: EB CF
        mov     si, 4664h                                      ;#3BC3: BE 64 46
        mov     di, si                                         ;#3BC6: 8B FE
        xor     ch, ch                                         ;#3BC8: 32 ED
        call    near 3C23h                                     ;#3BCA: E8 56 00
        mov     si, di                                         ;#3BCD: 8B F7
        lodsb                                                  ;#3BCF: AC
        call    near 2FE7h                                     ;#3BD0: E8 14 F4
        jz      short 3BDDh                                    ;#3BD3: 74 08
        mov     [di], al                                       ;#3BD5: 88 05
        inc     di                                             ;#3BD7: 47
        cmp     al, 0Dh                                        ;#3BD8: 3C 0D
        jnz     short 3BCFh                                    ;#3BDA: 75 F3
        ret                                                    ;#3BDC: C3
        cmp     al, 22h                                        ;#3BDD: 3C 22
        jnz     short 3BE6h                                    ;#3BDF: 75 05
        call    near 3C31h                                     ;#3BE1: E8 4D 00
        jmp     short 3BCFh                                    ;#3BE4: EB E9
        cmp     al, 3Eh                                        ;#3BE6: 3C 3E
        jnz     short 3BF1h                                    ;#3BE8: 75 07
        call    near 3C49h                                     ;#3BEA: E8 5C 00
        jb      short 3C17h                                    ;#3BED: 72 28
        jmp     short 3BCFh                                    ;#3BEF: EB DE
        cmp     al, 3Ch                                        ;#3BF1: 3C 3C
        jnz     short 3BFCh                                    ;#3BF3: 75 07
        call    near 3C43h                                     ;#3BF5: E8 4B 00
        jb      short 3C17h                                    ;#3BF8: 72 1D
        jmp     short 3BCFh                                    ;#3BFA: EB D3
        or      byte [es:339h], 2                              ;#3BFC: 26 80 0E 39 03 02
        call    near 302Ah                                     ;#3C02: E8 25 F4
        jz      short 3C1Dh                                    ;#3C05: 74 16
        cmp     al, 7Ch                                        ;#3C07: 3C 7C
        jz      short 3C1Dh                                    ;#3C09: 74 12
        mov     al, 7Ch                                        ;#3C0B: B0 7C
        cmp     [di-1], al                                     ;#3C0D: 38 45 FF
        jz      short 3C1Dh                                    ;#3C10: 74 0B
        mov     [di], al                                       ;#3C12: 88 05
        inc     di                                             ;#3C14: 47
        jmp     short 3BCFh                                    ;#3C15: EB B8
        mov     dx, 259h                                       ;#3C17: BA 59 02
        jmp     near 2EE9h                                     ;#3C1A: E9 CC F2
        mov     dx, 2B4h                                       ;#3C1D: BA B4 02
        jmp     near 2EE9h                                     ;#3C20: E9 C6 F2
        lodsb                                                  ;#3C23: AC
        cmp     al, 0Dh                                        ;#3C24: 3C 0D
        jz      short 3C30h                                    ;#3C26: 74 08
        cmp     al, 22h                                        ;#3C28: 3C 22
        jnz     short 3C23h                                    ;#3C2A: 75 F7
        inc     ch                                             ;#3C2C: FE C5
        jmp     short 3C23h                                    ;#3C2E: EB F3
        ret                                                    ;#3C30: C3
        dec     ch                                             ;#3C31: FE CD
        jz      short 3C3Fh                                    ;#3C33: 74 0A
        mov     [di], al                                       ;#3C35: 88 05
        inc     di                                             ;#3C37: 47
        lodsb                                                  ;#3C38: AC
        cmp     al, 22h                                        ;#3C39: 3C 22
        jnz     short 3C35h                                    ;#3C3B: 75 F8
        dec     ch                                             ;#3C3D: FE CD
        mov     [di], al                                       ;#3C3F: 88 05
        inc     di                                             ;#3C41: 47
        ret                                                    ;#3C42: C3
        push    di                                             ;#3C43: 57
        mov     di, 38Eh                                       ;#3C44: BF 8E 03
        jmp     short 3C5Ch                                    ;#3C47: EB 13
        push    di                                             ;#3C49: 57
        mov     di, 33Eh                                       ;#3C4A: BF 3E 03
        mov     byte [es:di-1], 0                              ;#3C4D: 26 C6 45 FF 00
        cmp     byte [si], 3Eh                                 ;#3C52: 80 3C 3E
        jnz     short 3C5Ch                                    ;#3C55: 75 05
        inc     byte [es:di-1]                                 ;#3C57: 26 FE 45 FF
        inc     si                                             ;#3C5B: 46
        call    near 3C61h                                     ;#3C5C: E8 02 00
        pop     di                                             ;#3C5F: 5F
        ret                                                    ;#3C60: C3
        mov     cl, 50h                                        ;#3C61: B1 50
        call    near 302Ah                                     ;#3C63: E8 C4 F3
        call    near 2FF6h                                     ;#3C66: E8 8D F3
        jz      short 3CA3h                                    ;#3C69: 74 38
        call    near 2FE7h                                     ;#3C6B: E8 79 F3
        jz      short 3CA3h                                    ;#3C6E: 74 33
        lodsb                                                  ;#3C70: AC
        cmp     byte [es:di], 0FFh                             ;#3C71: 26 80 3D FF
        jnz     short 3C79h                                    ;#3C75: 75 02
        mov     al, 0FFh                                       ;#3C77: B0 FF
        stosb                                                  ;#3C79: AA
        dec     cl                                             ;#3C7A: FE C9
        jnz     short 3C86h                                    ;#3C7C: 75 08
        mov     byte [es:di-50h], 0FFh                         ;#3C7E: 26 C6 45 B0 FF
        inc     cl                                             ;#3C83: FE C1
        dec     di                                             ;#3C85: 4F
        lodsb                                                  ;#3C86: AC
        call    near 2FF6h                                     ;#3C87: E8 6C F3
        jz      short 3C96h                                    ;#3C8A: 74 0A
        call    near 300Bh                                     ;#3C8C: E8 7C F3
        jz      short 3C96h                                    ;#3C8F: 74 05
        call    near 2FE7h                                     ;#3C91: E8 53 F3
        jnz     short 3C79h                                    ;#3C94: 75 E3
        dec     si                                             ;#3C96: 4E
        cmp     byte [es:di-1], 3Ah                            ;#3C97: 26 80 7D FF 3A
        jnz     short 3C9Fh                                    ;#3C9C: 75 01
        dec     di                                             ;#3C9E: 4F
        xor     al, al                                         ;#3C9F: 32 C0
        stosb                                                  ;#3CA1: AA
        ret                                                    ;#3CA2: C3
        mov     byte [es:di], 0FFh                             ;#3CA3: 26 C6 05 FF
        stc                                                    ;#3CA7: F9
        ret                                                    ;#3CA8: C3
        push    ax                                             ;#3CA9: 50
        push    bx                                             ;#3CAA: 53
        push    cx                                             ;#3CAB: 51
        push    dx                                             ;#3CAC: 52
        push    si                                             ;#3CAD: 56
        push    ds                                             ;#3CAE: 1E
        mov     ds, [cs:4660h]                                 ;#3CAF: 2E 8E 1E 60 46
        cmp     byte [33Bh], 0FFh                              ;#3CB4: 80 3E 3B 03 FF
        jnz     short 3CC8h                                    ;#3CB9: 75 0D
        cmp     byte [33Ch], 0FFh                              ;#3CBB: 80 3E 3C 03 FF
        jnz     short 3CC8h                                    ;#3CC0: 75 06
        call    near 3CCFh                                     ;#3CC2: E8 0A 00
        call    near 3D1Fh                                     ;#3CC5: E8 57 00
        pop     ds                                             ;#3CC8: 1F
        pop     si                                             ;#3CC9: 5E
        pop     dx                                             ;#3CCA: 5A
        pop     cx                                             ;#3CCB: 59
        pop     bx                                             ;#3CCC: 5B
        pop     ax                                             ;#3CCD: 58
        ret                                                    ;#3CCE: C3
        test    byte [339h], 2                                 ;#3CCF: F6 06 39 03 02
        jz      short 3D00h                                    ;#3CD4: 74 2A
        mov     si, [PIPE_NAME_PTRS]                           ;#3CD6: 8B 36 C8 04
        test    byte [339h], 1                                 ;#3CDA: F6 06 39 03 01
        jz      short 3CEEh                                    ;#3CDF: 74 0D
        test    byte [33Ah], 4                                 ;#3CE1: F6 06 3A 03 04
        jnz     short 3D00h                                    ;#3CE6: 75 18
        call    near 3D7Ah                                     ;#3CE8: E8 8F 00
        jb      short 3D13h                                    ;#3CEB: 72 26
        ret                                                    ;#3CED: C3
        test    byte [33Ah], 1                                 ;#3CEE: F6 06 3A 03 01
        jnz     short 3CFBh                                    ;#3CF3: 75 06
        call    near 3D7Ah                                     ;#3CF5: E8 82 00
        jb      short 3D13h                                    ;#3CF8: 72 19
        ret                                                    ;#3CFA: C3
        and     byte [33Ah], 0FEh                              ;#3CFB: 80 26 3A 03 FE
        mov     si, 38Eh                                       ;#3D00: BE 8E 03
        cmp     byte [si], 0                                   ;#3D03: 80 3C 00
        jz      short 3D12h                                    ;#3D06: 74 0A
        cmp     byte [si], 0FFh                                ;#3D08: 80 3C FF
        jz      short 3D19h                                    ;#3D0B: 74 0C
        call    near 3D7Ah                                     ;#3D0D: E8 6A 00
        jb      short 3D19h                                    ;#3D10: 72 07
        ret                                                    ;#3D12: C3
        mov     dx, 2E9h                                       ;#3D13: BA E9 02
        jmp     near 2EE9h                                     ;#3D16: E9 D0 F1
        mov     dx, 286h                                       ;#3D19: BA 86 02
        jmp     near 2EE9h                                     ;#3D1C: E9 CA F1
        test    byte [339h], 2                                 ;#3D1F: F6 06 39 03 02
        jz      short 3D57h                                    ;#3D24: 74 31
        mov     si, [4CAh]                                     ;#3D26: 8B 36 CA 04
        test    byte [339h], 1                                 ;#3D2A: F6 06 39 03 01
        jz      short 3D3Eh                                    ;#3D2F: 74 0D
        test    byte [33Ah], 8                                 ;#3D31: F6 06 3A 03 08
        jnz     short 3D57h                                    ;#3D36: 75 1F
        call    near 3D92h                                     ;#3D38: E8 57 00
        jb      short 3D13h                                    ;#3D3B: 72 D6
        ret                                                    ;#3D3D: C3
        test    byte [33Ah], 2                                 ;#3D3E: F6 06 3A 03 02
        jnz     short 3D52h                                    ;#3D43: 75 0D
        call    near 3DA8h                                     ;#3D45: E8 60 00
        mov     byte [si+3], 0                                 ;#3D48: C6 44 03 00
        call    near 3DAFh                                     ;#3D4C: E8 60 00
        jb      short 3D13h                                    ;#3D4F: 72 C2
        ret                                                    ;#3D51: C3
        and     byte [33Ah], 0FDh                              ;#3D52: 80 26 3A 03 FD
        mov     si, 33Eh                                       ;#3D57: BE 3E 03
        cmp     byte [si], 0                                   ;#3D5A: 80 3C 00
        jz      short 3D79h                                    ;#3D5D: 74 1A
        cmp     byte [si], 0FFh                                ;#3D5F: 80 3C FF
        jz      short 3D19h                                    ;#3D62: 74 B5
        cmp     byte [si-1], 0                                 ;#3D64: 80 7C FF 00
        jz      short 3D6Fh                                    ;#3D68: 74 05
        call    near 3D92h                                     ;#3D6A: E8 25 00
        jnb     short 3D74h                                    ;#3D6D: 73 05
        call    near 3DBDh                                     ;#3D6F: E8 4B 00
        jb      short 3D19h                                    ;#3D72: 72 A5
        mov     byte [33Dh], 1                                 ;#3D74: C6 06 3D 03 01
        ret                                                    ;#3D79: C3
        mov     dx, si                                         ;#3D7A: 8B D6
        mov     ax, 3D00h                                      ;#3D7C: B8 00 3D
        int     21h                                            ;#3D7F: CD 21
        jb      short 3D91h                                    ;#3D81: 72 0E
        mov     bx, ax                                         ;#3D83: 8B D8
        mov     al, 0FFh                                       ;#3D85: B0 FF
        xchg    [bx+18h], al                                   ;#3D87: 86 47 18
        xchg    [18h], al                                      ;#3D8A: 86 06 18 00
        mov     [33Bh], al                                     ;#3D8E: A2 3B 03
        ret                                                    ;#3D91: C3
        mov     dx, si                                         ;#3D92: 8B D6
        mov     ax, 3D01h                                      ;#3D94: B8 01 3D
        int     21h                                            ;#3D97: CD 21
        jb      short 3DD5h                                    ;#3D99: 72 3A
        xor     dx, dx                                         ;#3D9B: 33 D2
        xor     cx, cx                                         ;#3D9D: 33 C9
        mov     bx, ax                                         ;#3D9F: 8B D8
        mov     ax, 4202h                                      ;#3DA1: B8 02 42
        int     21h                                            ;#3DA4: CD 21
        jmp     short 3DC9h                                    ;#3DA6: EB 21
        mov     dx, si                                         ;#3DA8: 8B D6
        mov     ah, 41h                                        ;#3DAA: B4 41
        int     21h                                            ;#3DAC: CD 21
        ret                                                    ;#3DAE: C3
        xor     cx, cx                                         ;#3DAF: 33 C9
        mov     dx, si                                         ;#3DB1: 8B D6
        mov     ah, 5Ah                                        ;#3DB3: B4 5A
        int     21h                                            ;#3DB5: CD 21
        jb      short 3DD5h                                    ;#3DB7: 72 1C
        mov     bx, ax                                         ;#3DB9: 8B D8
        jmp     short 3DC9h                                    ;#3DBB: EB 0C
        xor     cx, cx                                         ;#3DBD: 33 C9
        mov     dx, si                                         ;#3DBF: 8B D6
        mov     ah, 3Ch                                        ;#3DC1: B4 3C
        int     21h                                            ;#3DC3: CD 21
        jb      short 3DD5h                                    ;#3DC5: 72 0E
        mov     bx, ax                                         ;#3DC7: 8B D8
        mov     al, 0FFh                                       ;#3DC9: B0 FF
        xchg    [bx+18h], al                                   ;#3DCB: 86 47 18
        xchg    [19h], al                                      ;#3DCE: 86 06 19 00
        mov     [33Ch], al                                     ;#3DD2: A2 3C 03
        ret                                                    ;#3DD5: C3
        mov     si, 4664h                                      ;#3DD6: BE 64 46
        mov     di, 4EEh                                       ;#3DD9: BF EE 04
        mov     [es:4ECh], di                                  ;#3DDC: 26 89 3E EC 04
        call    near 2F94h                                     ;#3DE1: E8 B0 F1
        mov     al, [4706h]                                    ;#3DE4: A0 06 47
        add     al, 41h                                        ;#3DE7: 04 41
        push    es                                             ;#3DE9: 06
        pop     ds                                             ;#3DEA: 1F
        mov     [PIPE_TEMP_NAME_1], al                         ;#3DEB: A2 CC 04
        mov     [PIPE_TEMP_NAME_2], al                         ;#3DEE: A2 DC 04
        mov     byte [33Ah], 85h                               ;#3DF1: C6 06 3A 03 85
        jmp     near 503Fh                                     ;#3DF6: E9 46 12
        mov     es, [4660h]                                    ;#3DF9: 8E 06 60 46
        cmp     byte [es:335h], 0                              ;#3DFD: 26 80 3E 35 03 00
        jz      short 3E28h                                    ;#3E03: 74 23
        mov     al, 0FFh                                       ;#3E05: B0 FF
        cmp     [es:33Bh], al                                  ;#3E07: 26 38 06 3B 03
        jnz     short 3E1Dh                                    ;#3E0C: 75 0F
        cmp     [es:33Ch], al                                  ;#3E0E: 26 38 06 3C 03
        jnz     short 3E1Dh                                    ;#3E13: 75 08
        test    byte [es:339h], 7                              ;#3E15: 26 F6 06 39 03 07
        jz      short 3E28h                                    ;#3E1B: 74 0B
        call    near 3094h                                     ;#3E1D: E8 74 F2
        jnb     short 3E28h                                    ;#3E20: 73 06
        mov     dx, 794h                                       ;#3E22: BA 94 07
        jmp     near 2EE9h                                     ;#3E25: E9 C1 F0
        test    byte [es:339h], 3                              ;#3E28: 26 F6 06 39 03 03
        jz      short 3E42h                                    ;#3E2E: 74 12
        and     byte [es:339h], 0FCh                           ;#3E30: 26 80 26 39 03 FC
        mov     byte [es:336h], 3                              ;#3E36: 26 C6 06 36 03 03
        mov     dx, 981h                                       ;#3E3C: BA 81 09
        call    near 39FDh                                     ;#3E3F: E8 BB FB
        or      byte [es:339h], 4                              ;#3E42: 26 80 0E 39 03 04
        mov     si, 473Ah                                      ;#3E48: BE 3A 47
        mov     di, AUTOEXEC_PATH                              ;#3E4B: BF E3 03
        mov     cx, 28h                                        ;#3E4E: B9 28 00
        rep     movsw                                          ;#3E51: F3 A5
        mov     di, 3DFh                                       ;#3E53: BF DF 03
        xor     ax, ax                                         ;#3E56: 33 C0
        stosw                                                  ;#3E58: AB
        stosw                                                  ;#3E59: AB
        mov     di, 433h                                       ;#3E5A: BF 33 04
        mov     cx, 0Ah                                        ;#3E5D: B9 0A 00
        rep     stosw                                          ;#3E60: F3 AB
        mov     si, 4664h                                      ;#3E62: BE 64 46
        mov     di, 447h                                       ;#3E65: BF 47 04
        mov     bx, 433h                                       ;#3E68: BB 33 04
        mov     cx, 0Ah                                        ;#3E6B: B9 0A 00
        call    near 302Ah                                     ;#3E6E: E8 B9 F1
        jz      short 3E8Fh                                    ;#3E71: 74 1C
        jcxz    3E7Ah                                          ;#3E73: E3 05
        mov     [es:bx], di                                    ;#3E75: 26 89 3F
        inc     bx                                             ;#3E78: 43
        inc     bx                                             ;#3E79: 43
        lodsb                                                  ;#3E7A: AC
        call    near 300Bh                                     ;#3E7B: E8 8D F1
        jz      short 3E87h                                    ;#3E7E: 74 07
        cmp     al, 0Dh                                        ;#3E80: 3C 0D
        jz      short 3E8Fh                                    ;#3E82: 74 0B
        stosb                                                  ;#3E84: AA
        jmp     short 3E7Ah                                    ;#3E85: EB F3
        xor     al, al                                         ;#3E87: 32 C0
        stosb                                                  ;#3E89: AA
        jcxz    3E6Eh                                          ;#3E8A: E3 E2
        dec     cx                                             ;#3E8C: 49
        jmp     short 3E6Eh                                    ;#3E8D: EB DF
        xor     ax, ax                                         ;#3E8F: 33 C0
        stosw                                                  ;#3E91: AB
        jmp     near 503Fh                                     ;#3E92: E9 AA 11
        test    byte [339h], 1                                 ;#3E95: F6 06 39 03 01
        jnz     short 3E9Dh                                    ;#3E9A: 75 01
        ret                                                    ;#3E9C: C3
        push    ds                                             ;#3E9D: 1E
        pop     es                                             ;#3E9E: 07
        mov     ah, 4Fh                                        ;#3E9F: B4 4F
        cmp     byte [5F5h], 0                                 ;#3EA1: 80 3E F5 05 00
        jnz     short 3EF2h                                    ;#3EA6: 75 4A
        mov     si, [5F0h]                                     ;#3EA8: 8B 36 F0 05
        mov     [5F2h], si                                     ;#3EAC: 89 36 F2 05
        mov     al, [si]                                       ;#3EB0: 8A 04
        or      al, al                                         ;#3EB2: 0A C0
        jnz     short 3ED0h                                    ;#3EB4: 75 1A
        and     byte [339h], 0FEh                              ;#3EB6: 80 26 39 03 FE
        jmp     near 503Fh                                     ;#3EBB: E9 81 11
        or      al, al                                         ;#3EBE: 0A C0
        jz      short 3EC9h                                    ;#3EC0: 74 07
        cmp     cl, 7Fh                                        ;#3EC2: 80 F9 7F
        jnb     short 3ECAh                                    ;#3EC5: 73 03
        stosb                                                  ;#3EC7: AA
        inc     cx                                             ;#3EC8: 41
        ret                                                    ;#3EC9: C3
        mov     dx, 7C5h                                       ;#3ECA: BA C5 07
        jmp     near 2EE9h                                     ;#3ECD: E9 19 F0
        lodsb                                                  ;#3ED0: AC
        call    near 2FE0h                                     ;#3ED1: E8 0C F1
        jnz     short 3EDBh                                    ;#3ED4: 75 05
        mov     byte [5F5h], 1                                 ;#3ED6: C6 06 F5 05 01
        or      al, al                                         ;#3EDB: 0A C0
        jnz     short 3ED0h                                    ;#3EDD: 75 F1
        mov     [5F0h], si                                     ;#3EDF: 89 36 F0 05
        cmp     byte [5F5h], 0                                 ;#3EE3: 80 3E F5 05 00
        jz      short 3F2Ch                                    ;#3EE8: 74 42
        mov     ah, 4Eh                                        ;#3EEA: B4 4E
        xor     ch, ch                                         ;#3EEC: 32 ED
        mov     cl, [5F4h]                                     ;#3EEE: 8A 0E F4 05
        push    ax                                             ;#3EF2: 50
        mov     dx, 5F6h                                       ;#3EF3: BA F6 05
        mov     ah, 1Ah                                        ;#3EF6: B4 1A
        int     21h                                            ;#3EF8: CD 21
        pop     ax                                             ;#3EFA: 58
        mov     dx, [5F2h]                                     ;#3EFB: 8B 16 F2 05
        int     21h                                            ;#3EFF: CD 21
        jnb     short 3F0Ah                                    ;#3F01: 73 07
        mov     byte [5F5h], 0                                 ;#3F03: C6 06 F5 05 00
        jmp     short 3E9Dh                                    ;#3F08: EB 93
        cmp     word [603h], 0FFFFh                            ;#3F0A: 83 3E 03 06 FF
        jz      short 3F03h                                    ;#3F0F: 74 F2
        cmp     byte [5F4h], 10h                               ;#3F11: 80 3E F4 05 10
        jnz     short 3F22h                                    ;#3F16: 75 0A
        mov     si, 5F6h                                       ;#3F18: BE F6 05
        call    near 3034h                                     ;#3F1B: E8 16 F1
        mov     ah, 4Fh                                        ;#3F1E: B4 4F
        jnb     short 3EFBh                                    ;#3F20: 73 D9
        mov     di, [5F2h]                                     ;#3F22: 8B 3E F2 05
        call    near 3209h                                     ;#3F26: E8 E0 F2
        xor     al, al                                         ;#3F29: 32 C0
        stosb                                                  ;#3F2B: AA
        mov     si, 5EEh                                       ;#3F2C: BE EE 05
        push    cs                                             ;#3F2F: 0E
        pop     es                                             ;#3F30: 07
        mov     di, 4664h                                      ;#3F31: BF 64 46
        xor     cx, cx                                         ;#3F34: 33 C9
        mov     al, [si]                                       ;#3F36: 8A 04
        dec     si                                             ;#3F38: 4E
        cmp     al, 25h                                        ;#3F39: 3C 25
        jz      short 3F63h                                    ;#3F3B: 74 26
        call    near 3EBEh                                     ;#3F3D: E8 7E FF
        jnz     short 3F36h                                    ;#3F40: 75 F4
        mov     al, 0Dh                                        ;#3F42: B0 0D
        stosb                                                  ;#3F44: AA
        test    byte [339h], 2                                 ;#3F45: F6 06 39 03 02
        jnz     short 3F61h                                    ;#3F4A: 75 15
        cmp     byte [279h], 0                                 ;#3F4C: 80 3E 79 02 00
        jz      short 3F61h                                    ;#3F51: 74 0E
        call    near 3A87h                                     ;#3F53: E8 31 FB
        push    cs                                             ;#3F56: 0E
        pop     ds                                             ;#3F57: 1F
        mov     dx, 4664h                                      ;#3F58: BA 64 46
        call    near 39E9h                                     ;#3F5B: E8 8B FA
        call    near 3AD6h                                     ;#3F5E: E8 75 FB
        stc                                                    ;#3F61: F9
        ret                                                    ;#3F62: C3
        mov     al, [si]                                       ;#3F63: 8A 04
        cmp     [5EFh], al                                     ;#3F65: 38 06 EF 05
        mov     al, 25h                                        ;#3F69: B0 25
        jnz     short 3F3Dh                                    ;#3F6B: 75 D0
        dec     si                                             ;#3F6D: 4E
        mov     bx, [5F2h]                                     ;#3F6E: 8B 1E F2 05
        mov     al, [bx]                                       ;#3F72: 8A 07
        inc     bx                                             ;#3F74: 43
        call    near 3EBEh                                     ;#3F75: E8 46 FF
        jnz     short 3F72h                                    ;#3F78: 75 F8
        cmp     byte [5F5h], 0                                 ;#3F7A: 80 3E F5 05 00
        jz      short 3F36h                                    ;#3F7F: 74 B5
        mov     bx, 614h                                       ;#3F81: BB 14 06
        mov     al, [bx]                                       ;#3F84: 8A 07
        inc     bx                                             ;#3F86: 43
        call    near 3EBEh                                     ;#3F87: E8 34 FF
        jnz     short 3F84h                                    ;#3F8A: 75 F8
        jmp     short 3F36h                                    ;#3F8C: EB A8
        test    byte [339h], 2                                 ;#3F8E: F6 06 39 03 02
        jnz     short 3F9Ch                                    ;#3F93: 75 07
        ret                                                    ;#3F95: C3
        mov     dx, 2B4h                                       ;#3F96: BA B4 02
        jmp     near 2EE9h                                     ;#3F99: E9 4D EF
        mov     si, [4ECh]                                     ;#3F9C: 8B 36 EC 04
        call    near 302Ah                                     ;#3FA0: E8 87 F0
        jnz     short 3FADh                                    ;#3FA3: 75 08
        and     byte [339h], 0FDh                              ;#3FA5: 80 26 39 03 FD
        jmp     near 503Fh                                     ;#3FAA: E9 92 10
        cmp     al, 7Ch                                        ;#3FAD: 3C 7C
        jz      short 3F96h                                    ;#3FAF: 74 E5
        mov     ax, [PIPE_NAME_PTRS]                           ;#3FB1: A1 C8 04
        xchg    [4CAh], ax                                     ;#3FB4: 87 06 CA 04
        mov     [PIPE_NAME_PTRS], ax                           ;#3FB8: A3 C8 04
        mov     di, 4664h                                      ;#3FBB: BF 64 46
        lodsb                                                  ;#3FBE: AC
        stosb                                                  ;#3FBF: AA
        cmp     al, 7Ch                                        ;#3FC0: 3C 7C
        jz      short 3FCEh                                    ;#3FC2: 74 0A
        cmp     al, 0Dh                                        ;#3FC4: 3C 0D
        jnz     short 3FBEh                                    ;#3FC6: 75 F6
        dec     si                                             ;#3FC8: 4E
        or      byte [33Ah], 0Ah                               ;#3FC9: 80 0E 3A 03 0A
        mov     byte [es:di-1], 0Dh                            ;#3FCE: 26 C6 45 FF 0D
        mov     [4ECh], si                                     ;#3FD3: 89 36 EC 04
        stc                                                    ;#3FD7: F9
        ret                                                    ;#3FD8: C3
        test    byte [339h], 4                                 ;#3FD9: F6 06 39 03 04
        jnz     short 3FE1h                                    ;#3FDE: 75 01
        ret                                                    ;#3FE0: C3
        mov     byte [3DEh], 1                                 ;#3FE1: C6 06 DE 03 01
        call    near 40E1h                                     ;#3FE6: E8 F8 00
        jz      short 401Ch                                    ;#3FE9: 74 31
        call    near 4172h                                     ;#3FEB: E8 84 01
        cmp     al, 3Ah                                        ;#3FEE: 3C 3A
        jz      short 3FE1h                                    ;#3FF0: 74 EF
        cmp     al, 0Dh                                        ;#3FF2: 3C 0D
        jz      short 3FE1h                                    ;#3FF4: 74 EB
        cmp     al, 40h                                        ;#3FF6: 3C 40
        jnz     short 4002h                                    ;#3FF8: 75 08
        mov     byte [3DEh], 0                                 ;#3FFA: C6 06 DE 03 00
        call    near 41DDh                                     ;#3FFF: E8 DB 01
        mov     al, [es:di]                                    ;#4002: 26 8A 05
        cmp     al, 25h                                        ;#4005: 3C 25
        jz      short 4024h                                    ;#4007: 74 1B
        cmp     al, 0Dh                                        ;#4009: 3C 0D
        jz      short 4010h                                    ;#400B: 74 03
        inc     di                                             ;#400D: 47
        jmp     short 4002h                                    ;#400E: EB F2
        cmp     byte [3DEh], 0                                 ;#4010: 80 3E DE 03 00
        jz      short 401Ah                                    ;#4015: 74 03
        call    near 3F4Ch                                     ;#4017: E8 32 FF
        stc                                                    ;#401A: F9
        ret                                                    ;#401B: C3
        and     byte [339h], 0FBh                              ;#401C: 80 26 39 03 FB
        jmp     near 503Fh                                     ;#4021: E9 1B 10
        call    near 41DDh                                     ;#4024: E8 B6 01
        cmp     byte [es:di], 25h                              ;#4027: 26 80 3D 25
        jnz     short 4030h                                    ;#402B: 75 03
        inc     di                                             ;#402D: 47
        jmp     short 4002h                                    ;#402E: EB D2
        mov     dl, [es:di]                                    ;#4030: 26 8A 15
        sub     dl, 30h                                        ;#4033: 80 EA 30
        cmp     dl, 9                                          ;#4036: 80 FA 09
        jnbe    short 4061h                                    ;#4039: 77 26
        call    near 41DDh                                     ;#403B: E8 9F 01
        mov     al, dl                                         ;#403E: 8A C2
        cbw                                                    ;#4040: 98
        shl     ax, 1                                          ;#4041: D1 E0
        mov     si, 433h                                       ;#4043: BE 33 04
        add     si, ax                                         ;#4046: 03 F0
        mov     si, [si]                                       ;#4048: 8B 34
        or      si, si                                         ;#404A: 0B F6
        jz      short 4002h                                    ;#404C: 74 B4
        push    si                                             ;#404E: 56
        call    near 3135h                                     ;#404F: E8 E3 F0
        dec     si                                             ;#4052: 4E
        pop     dx                                             ;#4053: 5A
        call    near 41F2h                                     ;#4054: E8 9B 01
        jb      short 40B7h                                    ;#4057: 72 5E
        mov     si, dx                                         ;#4059: 8B F2
        mov     di, ax                                         ;#405B: 8B F8
        rep     movsb                                          ;#405D: F3 A4
        jmp     short 4002h                                    ;#405F: EB A1
        mov     si, di                                         ;#4061: 8B F7
        lodsb                                                  ;#4063: 26 AC
        cmp     al, 0Dh                                        ;#4065: 3C 0D
        jz      short 4010h                                    ;#4067: 74 A7
        cmp     al, 25h                                        ;#4069: 3C 25
        jnz     short 4063h                                    ;#406B: 75 F6
        sub     si, di                                         ;#406D: 2B F7
        push    ds                                             ;#406F: 1E
        push    di                                             ;#4070: 57
        push    si                                             ;#4071: 56
        mov     ds, [2Ch]                                      ;#4072: 8E 1E 2C 00
        xor     si, si                                         ;#4076: 33 F6
        lodsb                                                  ;#4078: AC
        mov     ah, al                                         ;#4079: 8A E0
        mov     al, [es:di]                                    ;#407B: 26 8A 05
        cmp     al, 25h                                        ;#407E: 3C 25
        jz      short 4091h                                    ;#4080: 74 0F
        cmp     ah, 3Dh                                        ;#4082: 80 FC 3D
        jz      short 40CCh                                    ;#4085: 74 45
        call    near 2F00h                                     ;#4087: E8 76 EE
        cmp     ah, al                                         ;#408A: 3A E0
        jnz     short 40CCh                                    ;#408C: 75 3E
        inc     di                                             ;#408E: 47
        jmp     short 4078h                                    ;#408F: EB E7
        cmp     ah, 3Dh                                        ;#4091: 80 FC 3D
        jnz     short 40CCh                                    ;#4094: 75 36
        push    si                                             ;#4096: 56
        push    si                                             ;#4097: 56
        call    near 3135h                                     ;#4098: E8 9A F0
        pop     cx                                             ;#409B: 59
        xchg    si, cx                                         ;#409C: 87 CE
        sub     cx, si                                         ;#409E: 2B CE
        dec     cx                                             ;#40A0: 49
        pop     si                                             ;#40A1: 5E
        pop     dx                                             ;#40A2: 5A
        cmp     cx, dx                                         ;#40A3: 3B CA
        jz      short 40B3h                                    ;#40A5: 74 0C
        jb      short 40BAh                                    ;#40A7: 72 11
        push    si                                             ;#40A9: 56
        push    cx                                             ;#40AA: 51
        mov     si, cx                                         ;#40AB: 8B F1
        inc     di                                             ;#40AD: 47
        call    near 41F2h                                     ;#40AE: E8 41 01
        pop     cx                                             ;#40B1: 59
        pop     si                                             ;#40B2: 5E
        pop     di                                             ;#40B3: 5F
        jnb     short 40C6h                                    ;#40B4: 73 10
        pop     ds                                             ;#40B6: 1F
        jmp     near 4149h                                     ;#40B7: E9 8F 00
        pop     di                                             ;#40BA: 5F
        push    si                                             ;#40BB: 56
        push    cx                                             ;#40BC: 51
        sub     dx, cx                                         ;#40BD: 2B D1
        mov     cx, dx                                         ;#40BF: 8B CA
        call    near 41E0h                                     ;#40C1: E8 1C 01
        pop     cx                                             ;#40C4: 59
        pop     si                                             ;#40C5: 5E
        rep     movsb                                          ;#40C6: F3 A4
        pop     ds                                             ;#40C8: 1F
        jmp     near 4002h                                     ;#40C9: E9 36 FF
        call    near 3135h                                     ;#40CC: E8 66 F0
        pop     ax                                             ;#40CF: 58
        pop     di                                             ;#40D0: 5F
        push    di                                             ;#40D1: 57
        push    ax                                             ;#40D2: 50
        cmp     byte [si], 0                                   ;#40D3: 80 3C 00
        jnz     short 4078h                                    ;#40D6: 75 A0
        pop     cx                                             ;#40D8: 59
        pop     di                                             ;#40D9: 5F
        pop     ds                                             ;#40DA: 1F
        call    near 41E0h                                     ;#40DB: E8 02 01
        jmp     near 4002h                                     ;#40DE: E9 21 FF
        mov     dx, [3DFh]                                     ;#40E1: 8B 16 DF 03
        add     dx, [3E1h]                                     ;#40E5: 03 16 E1 03
        rcr     dx, 1                                          ;#40E9: D1 DA
        inc     dx                                             ;#40EB: 42
        jz      short 4127h                                    ;#40EC: 74 39
        mov     byte [288h], 1                                 ;#40EE: C6 06 88 02 01
        mov     ax, 3D00h                                      ;#40F3: B8 00 3D
        mov     dx, AUTOEXEC_PATH                              ;#40F6: BA E3 03
        int     21h                                            ;#40F9: CD 21
        jb      short 4128h                                    ;#40FB: 72 2B
        mov     bx, ax                                         ;#40FD: 8B D8
        mov     ax, 4200h                                      ;#40FF: B8 00 42
        mov     cx, [3E1h]                                     ;#4102: 8B 0E E1 03
        mov     dx, [3DFh]                                     ;#4106: 8B 16 DF 03
        int     21h                                            ;#410A: CD 21
        push    ds                                             ;#410C: 1E
        push    es                                             ;#410D: 06
        pop     ds                                             ;#410E: 1F
        mov     ah, 3Fh                                        ;#410F: B4 3F
        mov     cx, 80h                                        ;#4111: B9 80 00
        mov     dx, 4664h                                      ;#4114: BA 64 46
        int     21h                                            ;#4117: CD 21
        pop     ds                                             ;#4119: 1F
        push    ax                                             ;#411A: 50
        mov     ah, 3Eh                                        ;#411B: B4 3E
        int     21h                                            ;#411D: CD 21
        pop     dx                                             ;#411F: 5A
        or      dx, dx                                         ;#4120: 0B D2
        mov     byte [288h], 0                                 ;#4122: C6 06 88 02 00
        ret                                                    ;#4127: C3
        mov     byte [288h], 0                                 ;#4128: C6 06 88 02 00
        call    far word [299h]                                ;#412D: FF 1E 99 02
        pushf                                                  ;#4131: 9C
        push    cs                                             ;#4132: 0E
        pop     ds                                             ;#4133: 1F
        mov     dx, 8DCh                                       ;#4134: BA DC 08
        call    near 39FDh                                     ;#4137: E8 C3 F8
        popf                                                   ;#413A: 9D
        jnb     short 4151h                                    ;#413B: 73 14
        mov     dx, 94Ah                                       ;#413D: BA 4A 09
        call    near 39FDh                                     ;#4140: E8 BA F8
        call    near 5071h                                     ;#4143: E8 2B 0F
        jmp     near 503Fh                                     ;#4146: E9 F6 0E
        push    cs                                             ;#4149: 0E
        pop     ds                                             ;#414A: 1F
        mov     dx, 8A7h                                       ;#414B: BA A7 08
        call    near 39FDh                                     ;#414E: E8 AC F8
        mov     ds, [4660h]                                    ;#4151: 8E 1E 60 46
        and     byte [339h], 0FBh                              ;#4155: 80 26 39 03 FB
        or      byte [336h], 4                                 ;#415A: 80 0E 36 03 04
        mov     dx, 912h                                       ;#415F: BA 12 09
        jmp     near 2EE9h                                     ;#4162: E9 84 ED
        mov     bx, di                                         ;#4165: 8B DF
        dec     bx                                             ;#4167: 4B
        mov     byte [es:bx], 0Dh                              ;#4168: 26 C6 07 0D
        mov     bp, 46E3h                                      ;#416C: BD E3 46
        sub     bp, bx                                         ;#416F: 2B EB
        ret                                                    ;#4171: C3
        mov     cx, dx                                         ;#4172: 8B CA
        mov     di, 4664h                                      ;#4174: BF 64 46
        mov     al, [es:di]                                    ;#4177: 26 8A 05
        inc     di                                             ;#417A: 47
        cmp     al, 0Dh                                        ;#417B: 3C 0D
        jz      short 4193h                                    ;#417D: 74 14
        cmp     al, 0Ah                                        ;#417F: 3C 0A
        jz      short 4193h                                    ;#4181: 74 10
        cmp     al, 1Ah                                        ;#4183: 3C 1A
        jz      short 41B5h                                    ;#4185: 74 2E
        dec     cx                                             ;#4187: 49
        jnz     short 4177h                                    ;#4188: 75 ED
        cmp     dx, 80h                                        ;#418A: 81 FA 80 00
        jnb     short 4149h                                    ;#418E: 73 B9
        inc     di                                             ;#4190: 47
        jmp     short 41B5h                                    ;#4191: EB 22
        call    near 4165h                                     ;#4193: E8 CF FF
        or      bp, bp                                         ;#4196: 0B ED
        jz      short 41C3h                                    ;#4198: 74 29
        add     dx, 4663h                                      ;#419A: 81 C2 63 46
        dec     di                                             ;#419E: 4F
        inc     di                                             ;#419F: 47
        cmp     di, dx                                         ;#41A0: 3B FA
        jnbe    short 41C3h                                    ;#41A2: 77 1F
        mov     al, [es:di]                                    ;#41A4: 26 8A 05
        cmp     al, 0Ah                                        ;#41A7: 3C 0A
        jz      short 419Fh                                    ;#41A9: 74 F4
        cmp     al, 0Dh                                        ;#41AB: 3C 0D
        jz      short 419Fh                                    ;#41AD: 74 F0
        cmp     al, 1Ah                                        ;#41AF: 3C 1A
        jz      short 41B8h                                    ;#41B1: 74 05
        jmp     short 41C3h                                    ;#41B3: EB 0E
        call    near 4165h                                     ;#41B5: E8 AD FF
        mov     ax, 0FFFFh                                     ;#41B8: B8 FF FF
        mov     [3DFh], ax                                     ;#41BB: A3 DF 03
        mov     [3E1h], ax                                     ;#41BE: A3 E1 03
        jmp     short 41D0h                                    ;#41C1: EB 0D
        sub     di, 4664h                                      ;#41C3: 81 EF 64 46
        add     [3DFh], di                                     ;#41C7: 01 3E DF 03
        adc     word [3E1h], 0                                 ;#41CB: 83 16 E1 03 00
        mov     di, 4663h                                      ;#41D0: BF 63 46
        inc     di                                             ;#41D3: 47
        mov     al, [es:di]                                    ;#41D4: 26 8A 05
        call    near 3004h                                     ;#41D7: E8 2A EE
        jz      short 41D3h                                    ;#41DA: 74 F7
        ret                                                    ;#41DC: C3
        mov     cx, 1                                          ;#41DD: B9 01 00
        push    di                                             ;#41E0: 57
        mov     si, di                                         ;#41E1: 8B F7
        add     si, cx                                         ;#41E3: 03 F1
        lodsb                                                  ;#41E5: 26 AC
        stosb                                                  ;#41E7: AA
        cmp     al, 0Dh                                        ;#41E8: 3C 0D
        jnz     short 41E5h                                    ;#41EA: 75 F9
        pop     di                                             ;#41EC: 5F
        add     bp, cx                                         ;#41ED: 03 E9
        sub     bx, cx                                         ;#41EF: 2B D9
        ret                                                    ;#41F1: C3
        sub     si, dx                                         ;#41F2: 2B F2
        cmp     si, bp                                         ;#41F4: 3B F5
        jnbe    short 4213h                                    ;#41F6: 77 1B
        sub     bp, si                                         ;#41F8: 2B EE
        push    si                                             ;#41FA: 56
        add     si, bx                                         ;#41FB: 03 F3
        xchg    si, bx                                         ;#41FD: 87 DE
        mov     ax, di                                         ;#41FF: 8B C7
        mov     di, bx                                         ;#4201: 8B FB
        mov     cx, si                                         ;#4203: 8B CE
        sub     cx, ax                                         ;#4205: 2B C8
        inc     cx                                             ;#4207: 41
        push    ds                                             ;#4208: 1E
        push    es                                             ;#4209: 06
        pop     ds                                             ;#420A: 1F
        std                                                    ;#420B: FD
        rep     movsb                                          ;#420C: F3 A4
        cld                                                    ;#420E: FC
        pop     ds                                             ;#420F: 1F
        pop     cx                                             ;#4210: 59
        clc                                                    ;#4211: F8
        ret                                                    ;#4212: C3
        stc                                                    ;#4213: F9
        ret                                                    ;#4214: C3
        cmp     word [289h], 0                                 ;#4215: 83 3E 89 02 00
        jnz     short 421Dh                                    ;#421A: 75 01
        ret                                                    ;#421C: C3
        mov     al, 80h                                        ;#421D: B0 80
        cmp     word [289h], 80h                               ;#421F: 81 3E 89 02 80 00
        jnz     short 4229h                                    ;#4225: 75 02
        mov     al, 40h                                        ;#4227: B0 40
        or      [339h], al                                     ;#4229: 08 06 39 03
        xor     si, si                                         ;#422D: 33 F6
        xchg    [289h], si                                     ;#422F: 87 36 89 02
        mov     di, 4664h                                      ;#4233: BF 64 46
        call    near 2F94h                                     ;#4236: E8 5B ED
        stc                                                    ;#4239: F9
        ret                                                    ;#423A: C3
        call    near 3A87h                                     ;#423B: E8 49 F8
        mov     dx, 2B3h                                       ;#423E: BA B3 02
        mov     ah, 0Ah                                        ;#4241: B4 0A
        int     21h                                            ;#4243: CD 21
        mov     si, 2B5h                                       ;#4245: BE B5 02
        mov     di, 4664h                                      ;#4248: BF 64 46
        mov     cx, 40h                                        ;#424B: B9 40 00
        rep     movsw                                          ;#424E: F3 A5
        jmp     near 3AD6h                                     ;#4250: E9 83 F8
        push    si                                             ;#4253: 56
        push    di                                             ;#4254: 57
        push    ax                                             ;#4255: 50
        mov     di, 4E3Dh                                      ;#4256: BF 3D 4E
        mov     ax, 2901h                                      ;#4259: B8 01 29
        int     21h                                            ;#425C: CD 21
        pop     ax                                             ;#425E: 58
        pop     di                                             ;#425F: 5F
        pop     si                                             ;#4260: 5E
        ret                                                    ;#4261: C3
        call    near 349Eh                                     ;#4262: E8 39 F2
        jz      short 4283h                                    ;#4265: 74 1C
        stc                                                    ;#4267: F9
        js      short 4283h                                    ;#4268: 78 19
        dec     ah                                             ;#426A: FE CC
        mov     al, ah                                         ;#426C: 8A C4
        call    near 32E9h                                     ;#426E: E8 78 F0
        stc                                                    ;#4271: F9
        jnz     short 4283h                                    ;#4272: 75 0F
        call    near 2F0Bh                                     ;#4274: E8 94 EC
        clc                                                    ;#4277: F8
        jnz     short 4283h                                    ;#4278: 75 09
        mov     dl, ah                                         ;#427A: 8A D4
        mov     ah, 0Eh                                        ;#427C: B4 0E
        int     21h                                            ;#427E: CD 21
        jmp     near 503Fh                                     ;#4280: E9 BC 0D
        ret                                                    ;#4283: C3
        mov     di, 0C83h                                      ;#4284: BF 83 0C
        call    near 3140h                                     ;#4287: E8 B6 EE
        jcxz    42A9h                                          ;#428A: E3 1D
        mov     al, [si]                                       ;#428C: 8A 04
        call    near 2F18h                                     ;#428E: E8 87 EC
        jnz     short 42A9h                                    ;#4291: 75 16
        mov     dx, cx                                         ;#4293: 8B D1
        mov     di, 81h                                        ;#4295: BF 81 00
        call    near 2F94h                                     ;#4298: E8 F9 EC
        mov     [80h], cl                                      ;#429B: 88 0E 80 00
        mov     si, 81h                                        ;#429F: BE 81 00
        mov     bp, si                                         ;#42A2: 8B EE
        call    dx                                             ;#42A4: FF D2
        jmp     near 503Fh                                     ;#42A6: E9 96 0D
        ret                                                    ;#42A9: C3
        stc                                                    ;#42AA: F9
        ret                                                    ;#42AB: C3
        mov     bp, si                                         ;#42AC: 8B EE
        mov     di, 473Ah                                      ;#42AE: BF 3A 47
        call    near 330Ah                                     ;#42B1: E8 56 F0
        jb      short 42AAh                                    ;#42B4: 72 F4
        test    byte [472Dh], 8                                ;#42B6: F6 06 2D 47 08
        jnz     short 42AAh                                    ;#42BB: 75 ED
        test    byte [472Dh], 4                                ;#42BD: F6 06 2D 47 04
        jz      short 42AAh                                    ;#42C2: 74 E6
        mov     si, [472Fh]                                    ;#42C4: 8B 36 2F 47
        cmp     byte [si], 2Eh                                 ;#42C8: 80 3C 2E
        jz      short 42AAh                                    ;#42CB: 74 DD
        call    near 3050h                                     ;#42CD: E8 80 ED
        jz      short 42E2h                                    ;#42D0: 74 10
        push    si                                             ;#42D2: 56
        dec     si                                             ;#42D3: 4E
        mov     di, 0C3Dh                                      ;#42D4: BF 3D 0C
        call    near 3140h                                     ;#42D7: E8 66 EE
        pop     si                                             ;#42DA: 5E
        jcxz    42AAh                                          ;#42DB: E3 CD
        cmp     cl, 0FFh                                       ;#42DD: 80 F9 FF
        jb      short 42F6h                                    ;#42E0: 72 14
        cmp     si, 4786h                                      ;#42E2: 81 FE 86 47
        jnbe    short 42AAh                                    ;#42E6: 77 C2
        mov     word [si-1], 3F2Eh                             ;#42E8: C7 44 FF 2E 3F
        mov     word [si+1], 3F3Fh                             ;#42ED: C7 44 01 3F 3F
        mov     byte [si+3], 0                                 ;#42F2: C6 44 03 00
        push    es                                             ;#42F6: 06
        mov     word [4736h], 0                                ;#42F7: C7 06 36 47 00 00
        test    byte [472Dh], 2                                ;#42FD: F6 06 2D 47 02
        jnz     short 4319h                                    ;#4302: 75 15
        mov     si, 51Dh                                       ;#4304: BE 1D 05
        mov     cx, 5                                          ;#4307: B9 05 00
        call    near 311Ch                                     ;#430A: E8 0F EE
        jb      short 4319h                                    ;#430D: 72 0A
        add     di, cx                                         ;#430F: 03 F9
        mov     [4736h], di                                    ;#4311: 89 3E 36 47
        mov     [4738h], es                                    ;#4315: 8C 06 38 47
        pop     es                                             ;#4319: 07
        call    near 305Ch                                     ;#431A: E8 3F ED
        mov     si, 473Ah                                      ;#431D: BE 3A 47
        mov     di, 478Ah                                      ;#4320: BF 8A 47
        call    near 2FADh                                     ;#4323: E8 87 EC
        mov     si, [472Fh]                                    ;#4326: 8B 36 2F 47
        sub     si, 473Ah                                      ;#432A: 81 EE 3A 47
        add     si, 478Ah                                      ;#432E: 81 C6 8A 47
        mov     [4731h], si                                    ;#4332: 89 36 31 47
        test    byte [472Dh], 3                                ;#4336: F6 06 2D 47 03
        jz      short 4371h                                    ;#433B: 74 34
        test    byte [4E62h], 0FFh                             ;#433D: F6 06 62 4E FF
        jnz     short 4371h                                    ;#4342: 75 2D
        mov     byte [4E62h], 0FFh                             ;#4344: C6 06 62 4E FF
        push    si                                             ;#4349: 56
        push    di                                             ;#434A: 57
        mov     cx, 6                                          ;#434B: B9 06 00
        mov     di, 712h                                       ;#434E: BF 12 07
        lodsb                                                  ;#4351: AC
        call    near 2F00h                                     ;#4352: E8 AB EB
        cmp     al, [es:di]                                    ;#4355: 26 3A 05
        jnz     short 435Fh                                    ;#4358: 75 05
        pushf                                                  ;#435A: 9C
        inc     di                                             ;#435B: 47
        popf                                                   ;#435C: 9D
        loop    4351h                                          ;#435D: E2 F2
        pop     di                                             ;#435F: 5F
        pop     si                                             ;#4360: 5E
        jnz     short 4371h                                    ;#4361: 75 0E
        mov     si, [472Fh]                                    ;#4363: 8B 36 2F 47
        sub     si, 473Ah                                      ;#4367: 81 EE 3A 47
        add     si, [472Bh]                                    ;#436B: 03 36 2B 47
        clc                                                    ;#436F: F8
        ret                                                    ;#4370: C3
        call    near 3050h                                     ;#4371: E8 DC EC
        dec     si                                             ;#4374: 4E
        mov     [4733h], si                                    ;#4375: 89 36 33 47
        mov     byte [4735h], 0FFh                             ;#4379: C6 06 35 47 FF
        call    near 4447h                                     ;#437E: E8 C6 00
        jnb     short 4397h                                    ;#4381: 73 14
        call    near 3405h                                     ;#4383: E8 7F F0
        jnb     short 4379h                                    ;#4386: 73 F1
        ret                                                    ;#4388: C3
        call    near 4453h                                     ;#4389: E8 C7 00
        jnb     short 4397h                                    ;#438C: 73 09
        cmp     byte [4735h], 0FFh                             ;#438E: 80 3E 35 47 FF
        jz      short 4383h                                    ;#4393: 74 EE
        jmp     short 43C0h                                    ;#4395: EB 29
        mov     si, 47F8h                                      ;#4397: BE F8 47
        call    near 3050h                                     ;#439A: E8 B3 EC
        dec     si                                             ;#439D: 4E
        mov     di, 0C3Dh                                      ;#439E: BF 3D 0C
        push    si                                             ;#43A1: 56
        call    near 3140h                                     ;#43A2: E8 9B ED
        pop     si                                             ;#43A5: 5E
        jcxz    4389h                                          ;#43A6: E3 E1
        cmp     [4735h], cl                                    ;#43A8: 38 0E 35 47
        jbe     short 4389h                                    ;#43AC: 76 DB
        mov     [4735h], cl                                    ;#43AE: 88 0E 35 47
        mov     di, [4733h]                                    ;#43B2: 8B 3E 33 47
        call    near 2FADh                                     ;#43B6: E8 F4 EB
        cmp     byte [4735h], 0                                ;#43B9: 80 3E 35 47 00
        jnz     short 4389h                                    ;#43BE: 75 C9
        mov     si, 478Ah                                      ;#43C0: BE 8A 47
        mov     di, 473Ah                                      ;#43C3: BF 3A 47
        call    near 33E7h                                     ;#43C6: E8 1E F0
        mov     si, [4731h]                                    ;#43C9: 8B 36 31 47
        mov     di, si                                         ;#43CD: 8B FE
        call    near 2F86h                                     ;#43CF: E8 B4 EB
        cmp     byte [4735h], 2                                ;#43D2: 80 3E 35 47 02
        jb      short 43DCh                                    ;#43D7: 72 03
        jmp     near 3DF9h                                     ;#43D9: E9 1D FA
        mov     di, 81h                                        ;#43DC: BF 81 00
        call    near 2F9Fh                                     ;#43DF: E8 BD EB
        mov     [80h], cl                                      ;#43E2: 88 0E 80 00
        mov     bp, 81h                                        ;#43E6: BD 81 00
        call    near 301Fh                                     ;#43E9: E8 33 EC
        call    near 31F0h                                     ;#43EC: E8 01 EE
        mov     di, 5Ch                                        ;#43EF: BF 5C 00
        xchg    bp, si                                         ;#43F2: 87 F5
        mov     ax, 2901h                                      ;#43F4: B8 01 29
        int     21h                                            ;#43F7: CD 21
        xchg    si, bp                                         ;#43F9: 87 EE
        mov     al, [bp]                                       ;#43FB: 8A 46 00
        inc     bp                                             ;#43FE: 45
        call    near 300Bh                                     ;#43FF: E8 09 EC
        jz      short 440Ah                                    ;#4402: 74 06
        call    near 2FF6h                                     ;#4404: E8 EF EB
        jnz     short 43FBh                                    ;#4407: 75 F2
        dec     bp                                             ;#4409: 4D
        call    near 31F0h                                     ;#440A: E8 E3 ED
        mov     di, 6Ch                                        ;#440D: BF 6C 00
        xchg    bp, si                                         ;#4410: 87 F5
        mov     ax, 2901h                                      ;#4412: B8 01 29
        int     21h                                            ;#4415: CD 21
        xchg    si, bp                                         ;#4417: 87 EE
        call    near 3064h                                     ;#4419: E8 48 EC
        mov     es, [4660h]                                    ;#441C: 8E 06 60 46
        mov     byte [es:335h], 0                              ;#4420: 26 C6 06 35 03 00
        inc     byte [es:278h]                                 ;#4426: 26 FE 06 78 02
        mov     di, 5Ch                                        ;#442B: BF 5C 00
        mov     si, di                                         ;#442E: 8B F7
        mov     cx, 52h                                        ;#4430: B9 52 00
        rep     movsw                                          ;#4433: F3 A5
        mov     dx, 473Ah                                      ;#4435: BA 3A 47
        mov     bx, 2A5h                                       ;#4438: BB A5 02
        mov     ax, [es:2Ch]                                   ;#443B: 26 A1 2C 00
        mov     [es:bx], ax                                    ;#443F: 26 89 07
        jmp     far word [es:2A1h]                             ;#4442: 26 FF 2E A1 02
        mov     dx, 478Ah                                      ;#4447: BA 8A 47
        mov     cx, 2                                          ;#444A: B9 02 00
        mov     ah, 4Eh                                        ;#444D: B4 4E
        int     21h                                            ;#444F: CD 21
        jmp     short 4457h                                    ;#4451: EB 04
        mov     ah, 4Fh                                        ;#4453: B4 4F
        int     21h                                            ;#4455: CD 21
        jb      short 4462h                                    ;#4457: 72 09
        cmp     word [47E7h], 0FFFFh                           ;#4459: 83 3E E7 47 FF
        stc                                                    ;#445E: F9
        jz      short 4462h                                    ;#445F: 74 01
        clc                                                    ;#4461: F8
        ret                                                    ;#4462: C3
        push    ds                                             ;#4463: 1E
        mov     ds, [4660h]                                    ;#4464: 8E 1E 60 46
        mov     si, 200h                                       ;#4468: BE 00 02
        mov     di, 473Ah                                      ;#446B: BF 3A 47
        call    near 2FADh                                     ;#446E: E8 3C EB
        pop     ds                                             ;#4471: 1F
        jmp     near 43DCh                                     ;#4472: E9 67 FF
        mov     si, bp                                         ;#4475: 8B F5
        call    near 44C9h                                     ;#4477: E8 4F 00
        jb      short 44C6h                                    ;#447A: 72 4A
        test    word [4863h], 4                                ;#447C: F7 06 63 48 04 00
        jnz     short 4497h                                    ;#4482: 75 13
        mov     al, [48F2h]                                    ;#4484: A0 F2 48
        call    near 4CE2h                                     ;#4487: E8 58 08
        mov     dx, 48F9h                                      ;#448A: BA F9 48
        mov     ah, 1Ah                                        ;#448D: B4 1A
        int     21h                                            ;#448F: CD 21
        mov     di, 4893h                                      ;#4491: BF 93 48
        call    near 455Ch                                     ;#4494: E8 C5 00
        call    near 4523h                                     ;#4497: E8 89 00
        test    byte [48EEh], 80h                              ;#449A: F6 06 EE 48 80
        jnz     short 44C0h                                    ;#449F: 75 1F
        mov     dx, 4893h                                      ;#44A1: BA 93 48
        mov     cx, 10h                                        ;#44A4: B9 10 00
        test    word [4863h], 1                                ;#44A7: F7 06 63 48 01 00
        jz      short 44B1h                                    ;#44AD: 74 02
        xor     cx, cx                                         ;#44AF: 33 C9
        mov     ah, 4Eh                                        ;#44B1: B4 4E
        int     21h                                            ;#44B3: CD 21
        jb      short 44C0h                                    ;#44B5: 72 09
        call    near 4588h                                     ;#44B7: E8 CE 00
        mov     ah, 4Fh                                        ;#44BA: B4 4F
        int     21h                                            ;#44BC: CD 21
        jnb     short 44B7h                                    ;#44BE: 73 F7
        call    near 46FAh                                     ;#44C0: E8 37 02
        jmp     near 470Bh                                     ;#44C3: E9 45 02
        jmp     near 2EE9h                                     ;#44C6: E9 20 EA
        mov     di, 0C2Dh                                      ;#44C9: BF 2D 0C
        mov     ax, 4C5h                                       ;#44CC: B8 C5 04
        call    near 31A4h                                     ;#44CF: E8 D2 EC
        jb      short 44FCh                                    ;#44D2: 72 28
        mov     [4863h], ax                                    ;#44D4: A3 63 48
        mov     di, 4893h                                      ;#44D7: BF 93 48
        mov     ah, 0Fh                                        ;#44DA: B4 0F
        add     ah, 0F0h                                       ;#44DC: 80 C4 F0
        call    near 34F6h                                     ;#44DF: E8 14 F0
        jnb     short 44E9h                                    ;#44E2: 73 05
        and     bh, 0FBh                                       ;#44E4: 80 E7 FB
        jnz     short 4506h                                    ;#44E7: 75 1D
        mov     di, 0C2Dh                                      ;#44E9: BF 2D 0C
        mov     ax, 4C5h                                       ;#44EC: B8 C5 04
        call    near 31A4h                                     ;#44EF: E8 B2 EC
        jb      short 44FCh                                    ;#44F2: 72 08
        jnz     short 4501h                                    ;#44F4: 75 0B
        or      [4863h], ax                                    ;#44F6: 09 06 63 48
        clc                                                    ;#44FA: F8
        ret                                                    ;#44FB: C3
        mov     dx, 184h                                       ;#44FC: BA 84 01
        stc                                                    ;#44FF: F9
        ret                                                    ;#4500: C3
        mov     dx, 15Ch                                       ;#4501: BA 5C 01
        stc                                                    ;#4504: F9
        ret                                                    ;#4505: C3
        mov     dx, 141h                                       ;#4506: BA 41 01
        test    bh, 1                                          ;#4509: F6 C7 01
        jnz     short 4521h                                    ;#450C: 75 13
        mov     dx, 1C2h                                       ;#450E: BA C2 01
        test    bh, 80h                                        ;#4511: F6 C7 80
        jnz     short 4521h                                    ;#4514: 75 0B
        mov     dx, 559h                                       ;#4516: BA 59 05
        test    bh, 40h                                        ;#4519: F6 C7 40
        jnz     short 4521h                                    ;#451C: 75 03
        mov     dx, 9E9h                                       ;#451E: BA E9 09
        stc                                                    ;#4521: F9
        ret                                                    ;#4522: C3
        call    near 47A9h                                     ;#4523: E8 83 02
        test    al, 80h                                        ;#4526: A8 80
        mov     al, 17h                                        ;#4528: B0 17
        jz      short 452Eh                                    ;#452A: 74 02
        mov     al, 30h                                        ;#452C: B0 30
        mov     [4867h], al                                    ;#452E: A2 67 48
        mov     [4868h], al                                    ;#4531: A2 68 48
        mov     al, 1                                          ;#4534: B0 01
        test    word [4863h], 400h                             ;#4536: F7 06 63 48 00 04
        jz      short 4547h                                    ;#453C: 74 09
        mov     al, 5                                          ;#453E: B0 05
        cmp     ah, 50h                                        ;#4540: 80 FC 50
        jz      short 4547h                                    ;#4543: 74 02
        mov     al, 2                                          ;#4545: B0 02
        mov     [4865h], al                                    ;#4547: A2 65 48
        mov     [4866h], al                                    ;#454A: A2 66 48
        xor     ax, ax                                         ;#454D: 33 C0
        mov     [4869h], ax                                    ;#454F: A3 69 48
        mov     [486Bh], ax                                    ;#4552: A3 6B 48
        mov     [486Dh], ax                                    ;#4555: A3 6D 48
        mov     [486Fh], ax                                    ;#4558: A3 6F 48
        ret                                                    ;#455B: C3
        push    ds                                             ;#455C: 1E
        push    es                                             ;#455D: 06
        pop     ds                                             ;#455E: 1F
        mov     dx, di                                         ;#455F: 8B D7
        mov     di, [di+60h]                                   ;#4561: 8B 7D 60
        cmp     byte [di-2], 3Ah                               ;#4564: 80 7D FE 3A
        jz      short 456Bh                                    ;#4568: 74 01
        dec     di                                             ;#456A: 4F
        xor     al, al                                         ;#456B: 32 C0
        xchg    [di], al                                       ;#456D: 86 05
        push    ds                                             ;#456F: 1E
        push    dx                                             ;#4570: 52
        push    cs                                             ;#4571: 0E
        pop     ds                                             ;#4572: 1F
        mov     dx, 35Ah                                       ;#4573: BA 5A 03
        call    near 39EEh                                     ;#4576: E8 75 F4
        pop     dx                                             ;#4579: 5A
        pop     ds                                             ;#457A: 1F
        call    near 39E4h                                     ;#457B: E8 66 F4
        call    near 3AD6h                                     ;#457E: E8 55 F5
        call    near 3AD6h                                     ;#4581: E8 52 F5
        xchg    [di], al                                       ;#4584: 86 05
        pop     ds                                             ;#4586: 1F
        ret                                                    ;#4587: C3
        mov     si, 4893h                                      ;#4588: BE 93 48
        test    byte [si+7Bh], 10h                             ;#458B: F6 44 7B 10
        jnz     short 45AFh                                    ;#458F: 75 1E
        test    word [4863h], 80h                              ;#4591: F7 06 63 48 80 00
        jnz     short 45C7h                                    ;#4597: 75 2E
        inc     word [4869h]                                   ;#4599: FF 06 69 48
        mov     ax, [si+80h]                                   ;#459D: 8B 84 80 00
        add     [486Dh], ax                                    ;#45A1: 01 06 6D 48
        mov     ax, [si+82h]                                   ;#45A5: 8B 84 82 00
        adc     [486Fh], ax                                    ;#45A9: 11 06 6F 48
        jmp     short 45CCh                                    ;#45AD: EB 1D
        test    word [4863h], 1                                ;#45AF: F7 06 63 48 01 00
        jnz     short 45C7h                                    ;#45B5: 75 10
        add     si, 66h                                        ;#45B7: 83 C6 66
        call    near 3034h                                     ;#45BA: E8 77 EA
        jb      short 45C8h                                    ;#45BD: 72 09
        test    word [4863h], 80h                              ;#45BF: F7 06 63 48 80 00
        jz      short 45CCh                                    ;#45C5: 74 05
        ret                                                    ;#45C7: C3
        inc     word [486Bh]                                   ;#45C8: FF 06 6B 48
        call    near 45ECh                                     ;#45CC: E8 1D 00
        test    word [4863h], 400h                             ;#45CF: F7 06 63 48 00 04
        jnz     short 45DDh                                    ;#45D5: 75 06
        call    near 464Ch                                     ;#45D7: E8 72 00
        call    near 4668h                                     ;#45DA: E8 8B 00
        call    near 46D5h                                     ;#45DD: E8 F5 00
        test    word [4863h], 40h                              ;#45E0: F7 06 63 48 40 00
        jz      short 45EBh                                    ;#45E6: 74 03
        call    near 46E9h                                     ;#45E8: E8 FE 00
        ret                                                    ;#45EB: C3
        mov     dx, 531h                                       ;#45EC: BA 31 05
        mov     al, [4865h]                                    ;#45EF: A0 65 48
        cmp     [4866h], al                                    ;#45F2: 38 06 66 48
        jz      short 45FBh                                    ;#45F6: 74 03
        mov     dx, 387h                                       ;#45F8: BA 87 03
        call    near 39EEh                                     ;#45FB: E8 F0 F3
        lea     si, [4917h]                                    ;#45FE: 8D 36 17 49
        mov     di, 4871h                                      ;#4602: BF 71 48
        cmp     byte [si], 2Eh                                 ;#4605: 80 3C 2E
        jnz     short 4614h                                    ;#4608: 75 0A
        mov     cx, 0Ch                                        ;#460A: B9 0C 00
        xor     ax, ax                                         ;#460D: 33 C0
        call    near 4635h                                     ;#460F: E8 23 00
        jmp     short 462Fh                                    ;#4612: EB 1B
        mov     cx, 8                                          ;#4614: B9 08 00
        mov     ah, 2Eh                                        ;#4617: B4 2E
        mov     al, 0                                          ;#4619: B0 00
        call    near 4635h                                     ;#461B: E8 17 00
        lodsb                                                  ;#461E: AC
        cmp     al, ah                                         ;#461F: 3A C4
        jz      short 4624h                                    ;#4621: 74 01
        dec     si                                             ;#4623: 4E
        mov     al, 20h                                        ;#4624: B0 20
        stosb                                                  ;#4626: AA
        xor     ax, ax                                         ;#4627: 33 C0
        mov     cx, 3                                          ;#4629: B9 03 00
        call    near 4635h                                     ;#462C: E8 06 00
        mov     dx, 4871h                                      ;#462F: BA 71 48
        jmp     near 39DAh                                     ;#4632: E9 A5 F3
        cmp     [si], ah                                       ;#4635: 38 24
        jz      short 4642h                                    ;#4637: 74 09
        cmp     [si], al                                       ;#4639: 38 04
        jz      short 4642h                                    ;#463B: 74 05
        movsb                                                  ;#463D: A4
        loop    4635h                                          ;#463E: E2 F5
        jmp     short 4648h                                    ;#4640: EB 06
        push    ax                                             ;#4642: 50
        mov     al, 20h                                        ;#4643: B0 20
        rep     stosb                                          ;#4645: F3 AA
        pop     ax                                             ;#4647: 58
        mov     [es:di], al                                    ;#4648: 26 88 05
        ret                                                    ;#464B: C3
        mov     si, 4893h                                      ;#464C: BE 93 48
        test    byte [si+7Bh], 10h                             ;#464F: F6 44 7B 10
        jz      short 465Bh                                    ;#4653: 74 06
        mov     dx, 36Bh                                       ;#4655: BA 6B 03
        jmp     near 39EEh                                     ;#4658: E9 93 F3
        mov     di, [si+82h]                                   ;#465B: 8B BC 82 00
        mov     si, [si+80h]                                   ;#465F: 8B B4 80 00
        mov     ah, 9                                          ;#4663: B4 09
        jmp     near 327Bh                                     ;#4665: E9 13 EC
        mov     si, 4893h                                      ;#4668: BE 93 48
        mov     dx, [si+7Eh]                                   ;#466B: 8B 54 7E
        or      dx, dx                                         ;#466E: 0B D2
        jnz     short 4673h                                    ;#4670: 75 01
        ret                                                    ;#4672: C3
        mov     di, 487Eh                                      ;#4673: BF 7E 48
        mov     al, 20h                                        ;#4676: B0 20
        stosb                                                  ;#4678: AA
        mov     ax, dx                                         ;#4679: 8B C2
        mov     bh, 10h                                        ;#467B: B7 10
        and     al, 1Fh                                        ;#467D: 24 1F
        call    near 326Ah                                     ;#467F: E8 E8 EB
        mov     al, 2Dh                                        ;#4682: B0 2D
        stosb                                                  ;#4684: AA
        mov     ax, dx                                         ;#4685: 8B C2
        mov     cl, 5                                          ;#4687: B1 05
        shr     ax, cl                                         ;#4689: D3 E8
        and     al, 0Fh                                        ;#468B: 24 0F
        dec     al                                             ;#468D: FE C8
        push    si                                             ;#468F: 56
        mov     si, 648h                                       ;#4690: BE 48 06
        call    near 3260h                                     ;#4693: E8 CA EB
        pop     si                                             ;#4696: 5E
        mov     al, 2Dh                                        ;#4697: B0 2D
        stosb                                                  ;#4699: AA
        mov     al, dh                                         ;#469A: 8A C6
        shr     al, 1                                          ;#469C: D0 E8
        add     al, 50h                                        ;#469E: 04 50
        cmp     al, 64h                                        ;#46A0: 3C 64
        jb      short 46A6h                                    ;#46A2: 72 02
        sub     al, 64h                                        ;#46A4: 2C 64
        call    near 326Ah                                     ;#46A6: E8 C1 EB
        mov     bx, [si+7Ch]                                   ;#46A9: 8B 5C 7C
        or      bx, bx                                         ;#46AC: 0B DB
        jz      short 46CCh                                    ;#46AE: 74 1C
        mov     al, 20h                                        ;#46B0: B0 20
        stosb                                                  ;#46B2: AA
        shr     bx, 1                                          ;#46B3: D1 EB
        shr     bx, 1                                          ;#46B5: D1 EB
        shr     bx, 1                                          ;#46B7: D1 EB
        shr     bl, 1                                          ;#46B9: D0 EB
        shr     bl, 1                                          ;#46BB: D0 EB
        mov     al, bh                                         ;#46BD: 8A C7
        mov     bh, 10h                                        ;#46BF: B7 10
        call    near 326Ah                                     ;#46C1: E8 A6 EB
        mov     al, 3Ah                                        ;#46C4: B0 3A
        stosb                                                  ;#46C6: AA
        mov     al, bl                                         ;#46C7: 8A C3
        call    near 326Ah                                     ;#46C9: E8 9E EB
        xor     al, al                                         ;#46CC: 32 C0
        stosb                                                  ;#46CE: AA
        mov     dx, 487Eh                                      ;#46CF: BA 7E 48
        jmp     near 39E4h                                     ;#46D2: E9 0F F3
        dec     byte [4866h]                                   ;#46D5: FE 0E 66 48
        jnz     short 46E8h                                    ;#46D9: 75 0D
        mov     al, [4865h]                                    ;#46DB: A0 65 48
        mov     [4866h], al                                    ;#46DE: A2 66 48
        call    near 3AD6h                                     ;#46E1: E8 F2 F3
        dec     byte [4868h]                                   ;#46E4: FE 0E 68 48
        ret                                                    ;#46E8: C3
        cmp     byte [4868h], 0                                ;#46E9: 80 3E 68 48 00
        jz      short 46F1h                                    ;#46EE: 74 01
        ret                                                    ;#46F0: C3
        mov     al, [4867h]                                    ;#46F1: A0 67 48
        mov     [4868h], al                                    ;#46F4: A2 68 48
        jmp     near 5071h                                     ;#46F7: E9 77 09
        mov     al, [4866h]                                    ;#46FA: A0 66 48
        cmp     al, [4865h]                                    ;#46FD: 3A 06 65 48
        jz      short 470Ah                                    ;#4701: 74 07
        dec     byte [4868h]                                   ;#4703: FE 0E 68 48
        call    near 3AD6h                                     ;#4707: E8 CC F3
        ret                                                    ;#470A: C3
        test    word [4863h], 4                                ;#470B: F7 06 63 48 04 00
        jz      short 4714h                                    ;#4711: 74 01
        ret                                                    ;#4713: C3
        test    word [4863h], 40h                              ;#4714: F7 06 63 48 40 00
        jz      short 4726h                                    ;#471A: 74 0A
        cmp     byte [4868h], 2                                ;#471C: 80 3E 68 48 02
        jnbe    short 4726h                                    ;#4721: 77 03
        call    near 5071h                                     ;#4723: E8 4B 09
        test    word [4863h], 80h                              ;#4726: F7 06 63 48 80 00
        jnz     short 475Fh                                    ;#472C: 75 31
        mov     si, [4869h]                                    ;#472E: 8B 36 69 48
        xor     di, di                                         ;#4732: 33 FF
        mov     ah, 6                                          ;#4734: B4 06
        call    near 327Bh                                     ;#4736: E8 42 EB
        mov     dx, 396h                                       ;#4739: BA 96 03
        cmp     word [4869h], 1                                ;#473C: 83 3E 69 48 01
        jnz     short 4746h                                    ;#4741: 75 03
        mov     dx, 38Ch                                       ;#4743: BA 8C 03
        call    near 39EEh                                     ;#4746: E8 A5 F2
        mov     si, [486Dh]                                    ;#4749: 8B 36 6D 48
        mov     di, [486Fh]                                    ;#474D: 8B 3E 6F 48
        mov     ah, 0Ah                                        ;#4751: B4 0A
        call    near 327Bh                                     ;#4753: E8 25 EB
        mov     dx, 3C9h                                       ;#4756: BA C9 03
        call    near 39EEh                                     ;#4759: E8 92 F2
        call    near 3AD6h                                     ;#475C: E8 77 F3
        mov     dx, 375h                                       ;#475F: BA 75 03
        test    word [4863h], 1                                ;#4762: F7 06 63 48 01 00
        jnz     short 4782h                                    ;#4768: 75 18
        mov     si, [486Bh]                                    ;#476A: 8B 36 6B 48
        xor     di, di                                         ;#476E: 33 FF
        mov     ah, 6                                          ;#4770: B4 06
        call    near 327Bh                                     ;#4772: E8 06 EB
        mov     dx, 3ACh                                       ;#4775: BA AC 03
        cmp     word [486Bh], 1                                ;#4778: 83 3E 6B 48 01
        jnz     short 4782h                                    ;#477D: 75 03
        mov     dx, 3A0h                                       ;#477F: BA A0 03
        call    near 39EEh                                     ;#4782: E8 69 F2
        mov     ah, 36h                                        ;#4785: B4 36
        mov     dl, [48F2h]                                    ;#4787: 8A 16 F2 48
        int     21h                                            ;#478B: CD 21
        mul     cx                                             ;#478D: F7 E1
        mul     bx                                             ;#478F: F7 E3
        mov     di, dx                                         ;#4791: 8B FA
        mov     si, ax                                         ;#4793: 8B F0
        mov     cx, 0Ah                                        ;#4795: B9 0A 00
        shr     di, 1                                          ;#4798: D1 EF
        rcr     si, 1                                          ;#479A: D1 DE
        loop    4798h                                          ;#479C: E2 FA
        mov     ah, 8                                          ;#479E: B4 08
        call    near 327Bh                                     ;#47A0: E8 D8 EA
        mov     dx, 3B8h                                       ;#47A3: BA B8 03
        jmp     near 39EEh                                     ;#47A6: E9 45 F2
        push    es                                             ;#47A9: 06
        mov     ax, 40h                                        ;#47AA: B8 40 00
        mov     es, ax                                         ;#47AD: 8E C0
        mov     ah, [es:4Ah]                                   ;#47AF: 26 8A 26 4A 00
        mov     al, [es:49h]                                   ;#47B4: 26 A0 49 00
        mov     bh, [es:62h]                                   ;#47B8: 26 8A 3E 62 00
        pop     es                                             ;#47BD: 07
        ret                                                    ;#47BE: C3
        mov     si, bp                                         ;#47BF: 8B F5
        mov     di, 0C2Dh                                      ;#47C1: BF 2D 0C
        mov     ax, 0D0h                                       ;#47C4: B8 D0 00
        call    near 31A4h                                     ;#47C7: E8 DA E9
        jb      short 483Bh                                    ;#47CA: 72 6F
        jz      short 4840h                                    ;#47CC: 74 72
        mov     [4891h], ax                                    ;#47CE: A3 91 48
        mov     di, 4893h                                      ;#47D1: BF 93 48
        mov     ah, 24h                                        ;#47D4: B4 24
        call    near 34F6h                                     ;#47D6: E8 1D ED
        jb      short 481Eh                                    ;#47D9: 72 43
        mov     bh, [48EEh]                                    ;#47DB: 8A 3E EE 48
        test    bh, 80h                                        ;#47DF: F6 C7 80
        jnz     short 4845h                                    ;#47E2: 75 61
        test    bl, 80h                                        ;#47E4: F6 C3 80
        jnz     short 4845h                                    ;#47E7: 75 5C
        cmp     byte [48F1h], 0                                ;#47E9: 80 3E F1 48 00
        jz      short 4840h                                    ;#47EE: 74 50
        mov     di, 0C2Dh                                      ;#47F0: BF 2D 0C
        mov     ax, 0D0h                                       ;#47F3: B8 D0 00
        call    near 31A4h                                     ;#47F6: E8 AB E9
        jb      short 483Bh                                    ;#47F9: 72 40
        jnz     short 4840h                                    ;#47FB: 75 43
        or      [4891h], ax                                    ;#47FD: 09 06 91 48
        test    bh, 48h                                        ;#4801: F6 C7 48
        jz      short 4850h                                    ;#4804: 74 4A
        test    word [4891h], 40h                              ;#4806: F7 06 91 48 40 00
        jnz     short 4850h                                    ;#480C: 75 42
        mov     di, [48F3h]                                    ;#480E: 8B 3E F3 48
        mov     ax, [4891h]                                    ;#4812: A1 91 48
        and     ax, 80h                                        ;#4815: 25 80 00
        call    near 48E1h                                     ;#4818: E8 C6 00
        jnb     short 4850h                                    ;#481B: 73 33
        ret                                                    ;#481D: C3
        mov     dx, 141h                                       ;#481E: BA 41 01
        test    bh, 1                                          ;#4821: F6 C7 01
        jnz     short 484Dh                                    ;#4824: 75 27
        mov     dx, 1C2h                                       ;#4826: BA C2 01
        test    bh, 80h                                        ;#4829: F6 C7 80
        jnz     short 484Dh                                    ;#482C: 75 1F
        mov     dx, 6A1h                                       ;#482E: BA A1 06
        test    bh, 40h                                        ;#4831: F6 C7 40
        jnz     short 484Dh                                    ;#4834: 75 17
        mov     dx, 9E9h                                       ;#4836: BA E9 09
        jmp     short 484Dh                                    ;#4839: EB 12
        mov     dx, 184h                                       ;#483B: BA 84 01
        jmp     short 484Dh                                    ;#483E: EB 0D
        mov     dx, 15Ch                                       ;#4840: BA 5C 01
        jmp     short 484Dh                                    ;#4843: EB 08
        mov     dx, 1A1h                                       ;#4845: BA A1 01
        jmp     short 484Dh                                    ;#4848: EB 03
        mov     dx, 206h                                       ;#484A: BA 06 02
        jmp     near 2EE9h                                     ;#484D: E9 99 E6
        test    word [4891h], 50h                              ;#4850: F7 06 91 48 50 00
        jnz     short 487Ch                                    ;#4856: 75 24
        mov     bl, [48F2h]                                    ;#4858: 8A 1E F2 48
        mov     ax, 4409h                                      ;#485C: B8 09 44
        int     21h                                            ;#485F: CD 21
        test    dx, 1000h                                      ;#4861: F7 C2 00 10
        jnz     short 487Ch                                    ;#4865: 75 15
        mov     dx, 4893h                                      ;#4867: BA 93 48
        mov     cx, 20h                                        ;#486A: B9 20 00
        mov     ax, 41AAh                                      ;#486D: B8 AA 41
        int     21h                                            ;#4870: CD 21
        jnb     short 487Bh                                    ;#4872: 73 07
        cmp     ax, 5                                          ;#4874: 3D 05 00
        jz      short 484Ah                                    ;#4877: 74 D1
        jmp     short 4845h                                    ;#4879: EB CA
        ret                                                    ;#487B: C3
        mov     dx, 4893h                                      ;#487C: BA 93 48
        mov     cx, 20h                                        ;#487F: B9 20 00
        mov     ah, 4Eh                                        ;#4882: B4 4E
        int     21h                                            ;#4884: CD 21
        jb      short 4845h                                    ;#4886: 72 BD
        lea     si, [4917h]                                    ;#4888: 8D 36 17 49
        mov     di, [48F3h]                                    ;#488C: 8B 3E F3 48
        call    near 2FADh                                     ;#4890: E8 1A E7
        test    word [4891h], 40h                              ;#4893: F7 06 91 48 40 00
        jz      short 48AFh                                    ;#4899: 74 14
        call    near 3AFEh                                     ;#489B: E8 60 F2
        mov     dx, 4893h                                      ;#489E: BA 93 48
        call    near 39E4h                                     ;#48A1: E8 40 F1
        mov     dx, 1E5h                                       ;#48A4: BA E5 01
        call    near 39E4h                                     ;#48A7: E8 3A F1
        call    near 4B10h                                     ;#48AA: E8 63 02
        jb      short 48DAh                                    ;#48AD: 72 2B
        test    word [4891h], 10h                              ;#48AF: F7 06 91 48 10 00
        jz      short 48C3h                                    ;#48B5: 74 0C
        call    near 3AFEh                                     ;#48B7: E8 44 F2
        mov     dx, 4893h                                      ;#48BA: BA 93 48
        call    near 39E4h                                     ;#48BD: E8 24 F1
        call    near 3AD6h                                     ;#48C0: E8 13 F2
        test    byte [490Eh], 1                                ;#48C3: F6 06 0E 49 01
        jnz     short 48D4h                                    ;#48C8: 75 0A
        mov     dx, 4893h                                      ;#48CA: BA 93 48
        mov     ax, 4100h                                      ;#48CD: B8 00 41
        int     21h                                            ;#48D0: CD 21
        jnb     short 48DAh                                    ;#48D2: 73 06
        mov     dx, 206h                                       ;#48D4: BA 06 02
        call    near 39FDh                                     ;#48D7: E8 23 F1
        mov     ah, 4Fh                                        ;#48DA: B4 4F
        int     21h                                            ;#48DC: CD 21
        jnb     short 4888h                                    ;#48DE: 73 A8
        ret                                                    ;#48E0: C3
        cmp     word [di], 2E2Ah                               ;#48E1: 81 3D 2A 2E
        jnz     short 48EDh                                    ;#48E5: 75 06
        cmp     word [di+2], 2Ah                               ;#48E7: 83 7D 02 2A
        jz      short 48FCh                                    ;#48EB: 74 0F
        or      ax, ax                                         ;#48ED: 0B C0
        jnz     short 4905h                                    ;#48EF: 75 14
        mov     dl, 0                                          ;#48F1: B2 00
        mov     ax, 1817h                                      ;#48F3: B8 17 18
        int     21h                                            ;#48F6: CD 21
        or      al, al                                         ;#48F8: 0A C0
        jz      short 4905h                                    ;#48FA: 74 09
        mov     dx, 225h                                       ;#48FC: BA 25 02
        call    near 39EEh                                     ;#48FF: E8 EC F0
        call    near 4B10h                                     ;#4902: E8 0B 02
        ret                                                    ;#4905: C3
        call    near 4B47h                                     ;#4906: E8 3E 02
        mov     word [4DF0h], 1                                ;#4909: C7 06 F0 4D 01 00
        mov     ax, 0F0h                                       ;#490F: B8 F0 00
        call    near 4C1Bh                                     ;#4912: E8 06 03
        jb      short 494Fh                                    ;#4915: 72 38
        jz      short 494Fh                                    ;#4917: 74 36
        mov     al, 1                                          ;#4919: B0 01
        call    near 4B59h                                     ;#491B: E8 3B 02
        jb      short 494Fh                                    ;#491E: 72 2F
        mov     di, 4C09h                                      ;#4920: BF 09 4C
        push    di                                             ;#4923: 57
        mov     si, 4B89h                                      ;#4924: BE 89 4B
        call    near 602Ch                                     ;#4927: E8 02 17
        pop     di                                             ;#492A: 5F
        call    near 3209h                                     ;#492B: E8 DB E8
        mov     [4DD1h], di                                    ;#492E: 89 3E D1 4D
        call    near 301Fh                                     ;#4932: E8 EA E6
        jz      short 4950h                                    ;#4935: 74 19
        mov     al, [4662h]                                    ;#4937: A0 62 46
        cmp     al, [bp]                                       ;#493A: 3A 46 00
        jz      short 4991h                                    ;#493D: 74 52
        mov     al, [472Dh]                                    ;#493F: A0 2D 47
        mov     [4DF2h], al                                    ;#4942: A2 F2 4D
        mov     di, 4C89h                                      ;#4945: BF 89 4C
        mov     al, 1                                          ;#4948: B0 01
        call    near 4B59h                                     ;#494A: E8 0C 02
        jnb     short 4958h                                    ;#494D: 73 09
        ret                                                    ;#494F: C3
        mov     dx, 15Ch                                       ;#4950: BA 5C 01
        call    near 4C07h                                     ;#4953: E8 B1 02
        stc                                                    ;#4956: F9
        ret                                                    ;#4957: C3
        mov     ax, 0F0h                                       ;#4958: B8 F0 00
        call    near 4C1Bh                                     ;#495B: E8 BD 02
        jb      short 494Fh                                    ;#495E: 72 EF
        jnz     short 4950h                                    ;#4960: 75 EE
        mov     di, 4DB6h                                      ;#4962: BF B6 4D
        mov     si, [4DCFh]                                    ;#4965: 8B 36 CF 4D
        call    near 602Ch                                     ;#4969: E8 C0 16
        mov     di, 4B89h                                      ;#496C: BF 89 4B
        mov     si, 4C09h                                      ;#496F: BE 09 4C
        test    byte [472Dh], 1                                ;#4972: F6 06 2D 47 01
        jnz     short 497Dh                                    ;#4977: 75 04
        mov     al, [si]                                       ;#4979: 8A 04
        mov     [di], al                                       ;#497B: 88 05
        mov     al, [si]                                       ;#497D: 8A 04
        cmp     al, [di]                                       ;#497F: 3A 05
        mov     dx, 141h                                       ;#4981: BA 41 01
        jnz     short 4994h                                    ;#4984: 75 0E
        mov     ax, [4DF0h]                                    ;#4986: A1 F0 4D
        and     ax, 0A0h                                       ;#4989: 25 A0 00
        cmp     ax, 0A0h                                       ;#498C: 3D A0 00
        jnz     short 4999h                                    ;#498F: 75 08
        mov     dx, 184h                                       ;#4991: BA 84 01
        call    near 4C07h                                     ;#4994: E8 70 02
        stc                                                    ;#4997: F9
        ret                                                    ;#4998: C3
        test    word [4DF0h], 80h                              ;#4999: F7 06 F0 4D 80 00
        jz      short 49A4h                                    ;#499F: 74 03
        jmp     near 4A42h                                     ;#49A1: E9 9E 00
        test    byte [472Dh], 2                                ;#49A4: F6 06 2D 47 02
        jnz     short 4991h                                    ;#49A9: 75 E6
        test    byte [4DF2h], 2                                ;#49AB: F6 06 F2 4D 02
        jz      short 49C8h                                    ;#49B0: 74 16
        inc     di                                             ;#49B2: 47
        inc     di                                             ;#49B3: 47
        inc     si                                             ;#49B4: 46
        inc     si                                             ;#49B5: 46
        lodsb                                                  ;#49B6: AC
        stosb                                                  ;#49B7: AA
        cmp     [4DD1h], si                                    ;#49B8: 39 36 D1 4D
        jnz     short 49B6h                                    ;#49BC: 75 F8
        mov     si, 4DB6h                                      ;#49BE: BE B6 4D
        mov     [4DCFh], di                                    ;#49C1: 89 3E CF 4D
        call    near 2FADh                                     ;#49C5: E8 E5 E5
        test    word [4DF0h], 20h                              ;#49C8: F7 06 F0 4D 20 00
        jz      short 49E4h                                    ;#49CE: 74 14
        test    byte [4DF2h], 8                                ;#49D0: F6 06 F2 4D 08
        jnz     short 4991h                                    ;#49D5: 75 BA
        test    byte [472Dh], 8                                ;#49D7: F6 06 2D 47 08
        jnz     short 4991h                                    ;#49DC: 75 B3
        and     word [4DF0h], 0FFFEh                           ;#49DE: 81 26 F0 4D FE FF
        mov     dx, 4C09h                                      ;#49E4: BA 09 4C
        call    near 4BACh                                     ;#49E7: E8 C2 01
        jb      short 4A2Dh                                    ;#49EA: 72 41
        cmp     word [4D96h], 0FFFFh                           ;#49EC: 83 3E 96 4D FF
        jnz     short 49F8h                                    ;#49F1: 75 05
        mov     dx, 1A1h                                       ;#49F3: BA A1 01
        jmp     short 4994h                                    ;#49F6: EB 9C
        mov     si, 4DA7h                                      ;#49F8: BE A7 4D
        mov     di, [4DD1h]                                    ;#49FB: 8B 3E D1 4D
        call    near 602Ch                                     ;#49FF: E8 2A 16
        mov     di, 4B89h                                      ;#4A02: BF 89 4B
        call    near 4AD0h                                     ;#4A05: E8 C8 00
        test    word [4DF0h], 40h                              ;#4A08: F7 06 F0 4D 40 00
        jz      short 4A15h                                    ;#4A0E: 74 05
        call    near 4AF0h                                     ;#4A10: E8 DD 00
        jb      short 4A2Eh                                    ;#4A13: 72 19
        mov     ah, 56h                                        ;#4A15: B4 56
        int     21h                                            ;#4A17: CD 21
        jnb     short 4A2Eh                                    ;#4A19: 73 13
        mov     dx, 1F1h                                       ;#4A1B: BA F1 01
        call    near 4C07h                                     ;#4A1E: E8 E6 01
        mov     dx, di                                         ;#4A21: 8B D7
        call    near 39F8h                                     ;#4A23: E8 D2 EF
        mov     dx, 202h                                       ;#4A26: BA 02 02
        call    near 39FDh                                     ;#4A29: E8 D1 EF
        stc                                                    ;#4A2C: F9
        ret                                                    ;#4A2D: C3
        jb      short 4A3Bh                                    ;#4A2E: 72 0B
        test    word [4DF0h], 10h                              ;#4A30: F7 06 F0 4D 10 00
        jz      short 4A3Bh                                    ;#4A36: 74 03
        call    near 4B33h                                     ;#4A38: E8 F8 00
        mov     ah, 4Fh                                        ;#4A3B: B4 4F
        int     21h                                            ;#4A3D: CD 21
        jnb     short 49ECh                                    ;#4A3F: 73 AB
        ret                                                    ;#4A41: C3
        mov     al, [472Dh]                                    ;#4A42: A0 2D 47
        test    al, 8                                          ;#4A45: A8 08
        jnz     short 4A74h                                    ;#4A47: 75 2B
        test    al, 4                                          ;#4A49: A8 04
        jz      short 4A64h                                    ;#4A4B: 74 17
        mov     dx, 4B89h                                      ;#4A4D: BA 89 4B
        call    near 4AB6h                                     ;#4A50: E8 63 00
        jb      short 4A74h                                    ;#4A53: 72 1F
        jnz     short 4A64h                                    ;#4A55: 75 0D
        cmp     word [4D96h], 0FFFFh                           ;#4A57: 83 3E 96 4D FF
        jnz     short 4A1Bh                                    ;#4A5C: 75 BD
        mov     dx, 1A1h                                       ;#4A5E: BA A1 01
        jmp     near 4994h                                     ;#4A61: E9 30 FF
        call    near 4BD4h                                     ;#4A64: E8 6D 01
        or      byte [472Dh], 8                                ;#4A67: 80 0E 2D 47 08
        mov     si, di                                         ;#4A6C: 8B F7
        mov     di, 4DB6h                                      ;#4A6E: BF B6 4D
        call    near 602Ch                                     ;#4A71: E8 B8 15
        mov     al, [4DF2h]                                    ;#4A74: A0 F2 4D
        test    al, 8                                          ;#4A77: A8 08
        jz      short 4A7Eh                                    ;#4A79: 74 03
        jmp     near 49C8h                                     ;#4A7B: E9 4A FF
        cmp     al, 1                                          ;#4A7E: 3C 01
        jnz     short 4A87h                                    ;#4A80: 75 05
        mov     di, 4B8Bh                                      ;#4A82: BF 8B 4B
        jmp     short 4AA7h                                    ;#4A85: EB 20
        test    al, 4                                          ;#4A87: A8 04
        jz      short 4A98h                                    ;#4A89: 74 0D
        mov     dx, 4C09h                                      ;#4A8B: BA 09 4C
        call    near 4AB6h                                     ;#4A8E: E8 25 00
        jb      short 4A1Bh                                    ;#4A91: 72 88
        jnz     short 4A98h                                    ;#4A93: 75 03
        jmp     near 49ECh                                     ;#4A95: E9 54 FF
        mov     di, 4C09h                                      ;#4A98: BF 09 4C
        call    near 4C01h                                     ;#4A9B: E8 63 01
        mov     al, [4663h]                                    ;#4A9E: A0 63 46
        cmp     [di-1], al                                     ;#4AA1: 38 45 FF
        jnz     short 4AA7h                                    ;#4AA4: 75 01
        dec     di                                             ;#4AA6: 4F
        call    near 4BF0h                                     ;#4AA7: E8 46 01
        or      byte [4DF2h], 8                                ;#4AAA: 80 0E F2 4D 08
        mov     [4DD1h], di                                    ;#4AAF: 89 3E D1 4D
        jmp     near 49C8h                                     ;#4AB3: E9 12 FF
        push    word [4DF0h]                                   ;#4AB6: FF 36 F0 4D
        mov     word [4DF0h], 0                                ;#4ABA: C7 06 F0 4D 00 00
        call    near 4BB9h                                     ;#4AC0: E8 F6 00
        pop     word [4DF0h]                                   ;#4AC3: 8F 06 F0 4D
        jb      short 4ACFh                                    ;#4AC7: 72 06
        test    byte [4D9Eh], 10h                              ;#4AC9: F6 06 9E 4D 10
        clc                                                    ;#4ACE: F8
        ret                                                    ;#4ACF: C3
        push    di                                             ;#4AD0: 57
        push    dx                                             ;#4AD1: 52
        test    byte [472Dh], 8                                ;#4AD2: F6 06 2D 47 08
        jz      short 4AEDh                                    ;#4AD7: 74 14
        call    near 3209h                                     ;#4AD9: E8 2D E7
        push    di                                             ;#4ADC: 57
        mov     si, 4DB6h                                      ;#4ADD: BE B6 4D
        call    near 602Ch                                     ;#4AE0: E8 49 15
        pop     di                                             ;#4AE3: 5F
        mov     si, di                                         ;#4AE4: 8B F7
        mov     di, [4DD1h]                                    ;#4AE6: 8B 3E D1 4D
        call    near 5D47h                                     ;#4AEA: E8 5A 12
        pop     dx                                             ;#4AED: 5A
        pop     di                                             ;#4AEE: 5F
        ret                                                    ;#4AEF: C3
        push    dx                                             ;#4AF0: 52
        call    near 3AFEh                                     ;#4AF1: E8 0A F0
        mov     dx, 4C09h                                      ;#4AF4: BA 09 4C
        call    near 39E4h                                     ;#4AF7: E8 EA EE
        call    near 3B12h                                     ;#4AFA: E8 15 F0
        call    near 4B02h                                     ;#4AFD: E8 02 00
        pop     dx                                             ;#4B00: 5A
        ret                                                    ;#4B01: C3
        push    dx                                             ;#4B02: 52
        mov     dx, 4B89h                                      ;#4B03: BA 89 4B
        call    near 39E4h                                     ;#4B06: E8 DB EE
        mov     dx, 1E5h                                       ;#4B09: BA E5 01
        call    near 39E4h                                     ;#4B0C: E8 D5 EE
        pop     dx                                             ;#4B0F: 5A
        push    dx                                             ;#4B10: 52
        mov     ax, 0C08h                                      ;#4B11: B8 08 0C
        int     21h                                            ;#4B14: CD 21
        call    near 2F00h                                     ;#4B16: E8 E7 E3
        mov     dl, 53h                                        ;#4B19: B2 53
        cmp     al, 53h                                        ;#4B1B: 3C 53
        clc                                                    ;#4B1D: F8
        jz      short 4B23h                                    ;#4B1E: 74 03
        mov     dl, 4Eh                                        ;#4B20: B2 4E
        stc                                                    ;#4B22: F9
        pushf                                                  ;#4B23: 9C
        mov     ah, 2                                          ;#4B24: B4 02
        int     21h                                            ;#4B26: CD 21
        mov     dl, 0Dh                                        ;#4B28: B2 0D
        int     21h                                            ;#4B2A: CD 21
        mov     dl, 0Ah                                        ;#4B2C: B2 0A
        int     21h                                            ;#4B2E: CD 21
        popf                                                   ;#4B30: 9D
        pop     dx                                             ;#4B31: 5A
        ret                                                    ;#4B32: C3
        push    dx                                             ;#4B33: 52
        call    near 3AFEh                                     ;#4B34: E8 C7 EF
        call    near 39E4h                                     ;#4B37: E8 AA EE
        call    near 3B12h                                     ;#4B3A: E8 D5 EF
        mov     dx, di                                         ;#4B3D: 8B D7
        call    near 39E4h                                     ;#4B3F: E8 A2 EE
        call    near 3AD6h                                     ;#4B42: E8 91 EF
        pop     dx                                             ;#4B45: 5A
        ret                                                    ;#4B46: C3
        xor     ax, ax                                         ;#4B47: 33 C0
        mov     [4DC8h], al                                    ;#4B49: A2 C8 4D
        mov     [4DF3h], al                                    ;#4B4C: A2 F3 4D
        mov     [4DC4h], al                                    ;#4B4F: A2 C4 4D
        mov     [4DF0h], ax                                    ;#4B52: A3 F0 4D
        mov     di, 4C89h                                      ;#4B55: BF 89 4C
        ret                                                    ;#4B58: C3
        push    ax                                             ;#4B59: 50
        call    near 330Ah                                     ;#4B5A: E8 AD E7
        jb      short 4B90h                                    ;#4B5D: 72 31
        mov     al, [472Dh]                                    ;#4B5F: A0 2D 47
        test    al, 80h                                        ;#4B62: A8 80
        jnz     short 4B99h                                    ;#4B64: 75 33
        test    al, 8                                          ;#4B66: A8 08
        jz      short 4B6Fh                                    ;#4B68: 74 05
        mov     byte [4DC8h], 1                                ;#4B6A: C6 06 C8 4D 01
        mov     si, 4C89h                                      ;#4B6F: BE 89 4C
        mov     di, 4B89h                                      ;#4B72: BF 89 4B
        pop     ax                                             ;#4B75: 58
        or      al, al                                         ;#4B76: 0A C0
        jnz     short 4B8Bh                                    ;#4B78: 75 11
        call    near 33E7h                                     ;#4B7A: E8 6A E8
        mov     si, 4B89h                                      ;#4B7D: BE 89 4B
        call    near 4B9Eh                                     ;#4B80: E8 1B 00
        mov     ax, [4731h]                                    ;#4B83: A1 31 47
        mov     [4DCFh], ax                                    ;#4B86: A3 CF 4D
        clc                                                    ;#4B89: F8
        ret                                                    ;#4B8A: C3
        call    near 33FEh                                     ;#4B8B: E8 70 E8
        jmp     short 4B7Dh                                    ;#4B8E: EB ED
        mov     dx, 1C2h                                       ;#4B90: BA C2 01
        call    near 4C07h                                     ;#4B93: E8 71 00
        pop     ax                                             ;#4B96: 58
        stc                                                    ;#4B97: F9
        ret                                                    ;#4B98: C3
        mov     dx, 141h                                       ;#4B99: BA 41 01
        jmp     short 4B93h                                    ;#4B9C: EB F5
        lodsb                                                  ;#4B9E: AC
        or      al, al                                         ;#4B9F: 0A C0
        jz      short 4BABh                                    ;#4BA1: 74 08
        call    near 2F00h                                     ;#4BA3: E8 5A E3
        mov     [si-1], al                                     ;#4BA6: 88 44 FF
        jmp     short 4B9Eh                                    ;#4BA9: EB F3
        ret                                                    ;#4BAB: C3
        call    near 4BB9h                                     ;#4BAC: E8 0A 00
        jnb     short 4BB8h                                    ;#4BAF: 73 07
        mov     dx, 1A1h                                       ;#4BB1: BA A1 01
        call    near 4C07h                                     ;#4BB4: E8 50 00
        stc                                                    ;#4BB7: F9
        ret                                                    ;#4BB8: C3
        mov     cx, 10h                                        ;#4BB9: B9 10 00
        test    word [4DF0h], 1                                ;#4BBC: F7 06 F0 4D 01 00
        jz      short 4BC6h                                    ;#4BC2: 74 02
        xor     cx, cx                                         ;#4BC4: 33 C9
        push    dx                                             ;#4BC6: 52
        mov     dx, 4D89h                                      ;#4BC7: BA 89 4D
        mov     ah, 1Ah                                        ;#4BCA: B4 1A
        int     21h                                            ;#4BCC: CD 21
        pop     dx                                             ;#4BCE: 5A
        mov     ah, 4Eh                                        ;#4BCF: B4 4E
        int     21h                                            ;#4BD1: CD 21
        ret                                                    ;#4BD3: C3
        mov     di, 4B89h                                      ;#4BD4: BF 89 4B
        call    near 4C01h                                     ;#4BD7: E8 27 00
        mov     al, [4663h]                                    ;#4BDA: A0 63 46
        cmp     [di-1], al                                     ;#4BDD: 38 45 FF
        jnz     short 4BE3h                                    ;#4BE0: 75 01
        dec     di                                             ;#4BE2: 4F
        call    near 4BF0h                                     ;#4BE3: E8 0A 00
        or      byte [4DC8h], 1                                ;#4BE6: 80 0E C8 4D 01
        mov     [4DCFh], di                                    ;#4BEB: 89 3E CF 4D
        ret                                                    ;#4BEF: C3
        mov     al, [4663h]                                    ;#4BF0: A0 63 46
        mov     [di], al                                       ;#4BF3: 88 05
        inc     di                                             ;#4BF5: 47
        mov     word [di], 2E2Ah                               ;#4BF6: C7 05 2A 2E
        mov     word [di+2], 2Ah                               ;#4BFA: C7 45 02 2A 00
        ret                                                    ;#4BFF: C3
        inc     di                                             ;#4C00: 47
        cmp     byte [di], 0                                   ;#4C01: 80 3D 00
        jnz     short 4C00h                                    ;#4C04: 75 FA
        ret                                                    ;#4C06: C3
        push    ds                                             ;#4C07: 1E
        mov     ds, [cs:4660h]                                 ;#4C08: 2E 8E 1E 60 46
        and     byte [339h], 0FCh                              ;#4C0D: 80 26 39 03 FC
        or      byte [336h], 3                                 ;#4C12: 80 0E 36 03 03
        pop     ds                                             ;#4C17: 1F
        jmp     near 39FDh                                     ;#4C18: E9 E2 ED
        call    near 31F2h                                     ;#4C1B: E8 D4 E5
        pushf                                                  ;#4C1E: 9C
        or      [4DF0h], ax                                    ;#4C1F: 09 06 F0 4D
        popf                                                   ;#4C23: 9D
        jnb     short 4C2Dh                                    ;#4C24: 73 07
        mov     dx, 184h                                       ;#4C26: BA 84 01
        call    near 4C07h                                     ;#4C29: E8 DB FF
        stc                                                    ;#4C2C: F9
        ret                                                    ;#4C2D: C3
        mov     byte [4C09h], 0                                ;#4C2E: C6 06 09 4C 00
        mov     byte [4DEEh], 1                                ;#4C33: C6 06 EE 4D 01
        call    near 5CD0h                                     ;#4C38: E8 95 10
        call    near 4B47h                                     ;#4C3B: E8 09 FF
        mov     byte [4DC4h], 8                                ;#4C3E: C6 06 C4 4D 08
        call    near 301Fh                                     ;#4C43: E8 D9 E3
        jz      short 4C68h                                    ;#4C46: 74 20
        mov     al, 1                                          ;#4C48: B0 01
        call    near 4B59h                                     ;#4C4A: E8 0C FF
        jb      short 4C59h                                    ;#4C4D: 72 0A
        call    near 301Fh                                     ;#4C4F: E8 CD E3
        jnz     short 4C68h                                    ;#4C52: 75 14
        call    near 6036h                                     ;#4C54: E8 DF 13
        jnb     short 4C5Ah                                    ;#4C57: 73 01
        ret                                                    ;#4C59: C3
        call    near 4C70h                                     ;#4C5A: E8 13 00
        mov     ah, 4Fh                                        ;#4C5D: B4 4F
        int     21h                                            ;#4C5F: CD 21
        jb      short 4C59h                                    ;#4C61: 72 F6
        call    near 5F9Ah                                     ;#4C63: E8 34 13
        jmp     short 4C5Ah                                    ;#4C66: EB F2
        mov     dx, 15Ch                                       ;#4C68: BA 5C 01
        call    near 4C07h                                     ;#4C6B: E8 99 FF
        stc                                                    ;#4C6E: F9
        ret                                                    ;#4C6F: C3
        call    near 607Ch                                     ;#4C70: E8 09 14
        mov     [4DDCh], dx                                    ;#4C73: 89 16 DC 4D
        mov     word [4DDEh], 0                                ;#4C77: C7 06 DE 4D 00 00
        mov     bx, [4DE2h]                                    ;#4C7D: 8B 1E E2 4D
        mov     byte [4DC4h], 29h                              ;#4C81: C6 06 C4 4D 29
        call    near 60CDh                                     ;#4C86: E8 44 14
        jb      short 4CA9h                                    ;#4C89: 72 1E
        call    near 6606h                                     ;#4C8B: E8 78 19
        call    near 63CBh                                     ;#4C8E: E8 3A 17
        jb      short 4CA5h                                    ;#4C91: 72 12
        push    word [4DC6h]                                   ;#4C93: FF 36 C6 4D
        mov     word [4DE4h], 1                                ;#4C97: C7 06 E4 4D 01 00
        call    near 64EBh                                     ;#4C9D: E8 4B 18
        pop     ax                                             ;#4CA0: 58
        or      al, al                                         ;#4CA1: 0A C0
        jnz     short 4C8Eh                                    ;#4CA3: 75 E9
        call    near 6176h                                     ;#4CA5: E8 CE 14
        ret                                                    ;#4CA8: C3
        call    near 5D3Ch                                     ;#4CA9: E8 90 10
        stc                                                    ;#4CAC: F9
        ret                                                    ;#4CAD: C3
        call    near 301Fh                                     ;#4CAE: E8 6E E3
        jz      short 4CDDh                                    ;#4CB1: 74 2A
        mov     di, 4B89h                                      ;#4CB3: BF 89 4B
        call    near 330Ah                                     ;#4CB6: E8 51 E6
        test    byte [472Dh], 80h                              ;#4CB9: F6 06 2D 47 80
        jnz     short 4CD1h                                    ;#4CBE: 75 11
        test    byte [472Dh], 10h                              ;#4CC0: F6 06 2D 47 10
        jz      short 4CD7h                                    ;#4CC5: 74 10
        call    near 301Fh                                     ;#4CC7: E8 55 E3
        jnz     short 4CD7h                                    ;#4CCA: 75 0B
        mov     al, [472Eh]                                    ;#4CCC: A0 2E 47
        jmp     short 4CE2h                                    ;#4CCF: EB 11
        mov     dx, 141h                                       ;#4CD1: BA 41 01
        jmp     near 2EE9h                                     ;#4CD4: E9 12 E2
        mov     dx, 15Ch                                       ;#4CD7: BA 5C 01
        jmp     near 2EE9h                                     ;#4CDA: E9 0C E2
        mov     al, [4706h]                                    ;#4CDD: A0 06 47
        inc     al                                             ;#4CE0: FE C0
        push    ax                                             ;#4CE2: 50
        push    cx                                             ;#4CE3: 51
        push    es                                             ;#4CE4: 06
        push    di                                             ;#4CE5: 57
        push    ds                                             ;#4CE6: 1E
        pop     es                                             ;#4CE7: 07
        mov     di, 4DF4h                                      ;#4CE8: BF F4 4D
        mov     al, 0FFh                                       ;#4CEB: B0 FF
        stosb                                                  ;#4CED: AA
        mov     cx, 5                                          ;#4CEE: B9 05 00
        xor     al, al                                         ;#4CF1: 32 C0
        rep     stosb                                          ;#4CF3: F3 AA
        mov     al, 8                                          ;#4CF5: B0 08
        stosb                                                  ;#4CF7: AA
        mov     al, 0                                          ;#4CF8: B0 00
        stosb                                                  ;#4CFA: AA
        mov     cx, 0Bh                                        ;#4CFB: B9 0B 00
        mov     al, 3Fh                                        ;#4CFE: B0 3F
        rep     stosb                                          ;#4D00: F3 AA
        mov     cx, 14h                                        ;#4D02: B9 14 00
        mov     al, 0                                          ;#4D05: B0 00
        rep     stosb                                          ;#4D07: F3 AA
        pop     di                                             ;#4D09: 5F
        pop     es                                             ;#4D0A: 07
        pop     cx                                             ;#4D0B: 59
        pop     ax                                             ;#4D0C: 58
        mov     [4DFBh], al                                    ;#4D0D: A2 FB 4D
        mov     bl, al                                         ;#4D10: 8A D8
        mov     dx, 4D89h                                      ;#4D12: BA 89 4D
        mov     ah, 1Ah                                        ;#4D15: B4 1A
        int     21h                                            ;#4D17: CD 21
        mov     dx, 4DF4h                                      ;#4D19: BA F4 4D
        mov     ah, 11h                                        ;#4D1C: B4 11
        int     21h                                            ;#4D1E: CD 21
        or      al, al                                         ;#4D20: 0A C0
        pushf                                                  ;#4D22: 9C
        mov     dx, 32Ch                                       ;#4D23: BA 2C 03
        call    near 39EEh                                     ;#4D26: E8 C5 EC
        mov     al, bl                                         ;#4D29: 8A C3
        dec     al                                             ;#4D2B: FE C8
        call    near 3B09h                                     ;#4D2D: E8 D9 ED
        popf                                                   ;#4D30: 9D
        jnz     short 4D47h                                    ;#4D31: 75 14
        mov     dx, 346h                                       ;#4D33: BA 46 03
        call    near 39EEh                                     ;#4D36: E8 B5 EC
        mov     byte [4D9Ch], 0                                ;#4D39: C6 06 9C 4D 00
        mov     dx, 4D91h                                      ;#4D3E: BA 91 4D
        call    near 39E4h                                     ;#4D41: E8 A0 EC
        jmp     near 3AD6h                                     ;#4D44: E9 8F ED
        mov     dx, 34Ah                                       ;#4D47: BA 4A 03
        jmp     near 39EEh                                     ;#4D4A: E9 A1 EC
        call    near 4E4Fh                                     ;#4D4D: E8 FF 00
        jcxz    4D5Bh                                          ;#4D50: E3 09
        mov     ds, [4660h]                                    ;#4D52: 8E 1E 60 46
        mov     [279h], cl                                     ;#4D56: 88 0E 79 02
        ret                                                    ;#4D5A: C3
        cmp     byte [80h], 0                                  ;#4D5B: 80 3E 80 00 00
        jz      short 4D6Bh                                    ;#4D60: 74 09
        mov     dx, 82h                                        ;#4D62: BA 82 00
        call    near 39E9h                                     ;#4D65: E8 81 EC
        jmp     near 3AD6h                                     ;#4D68: E9 6B ED
        push    ds                                             ;#4D6B: 1E
        mov     ds, [4660h]                                    ;#4D6C: 8E 1E 60 46
        mov     al, [279h]                                     ;#4D70: A0 79 02
        pop     ds                                             ;#4D73: 1F
        mov     dx, 45Ah                                       ;#4D74: BA 5A 04
        jmp     short 4D92h                                    ;#4D77: EB 19
        call    near 4E4Fh                                     ;#4D79: E8 D3 00
        jcxz    4D86h                                          ;#4D7C: E3 08
        mov     dl, cl                                         ;#4D7E: 8A D1
        mov     ax, 3301h                                      ;#4D80: B8 01 33
        int     21h                                            ;#4D83: CD 21
        ret                                                    ;#4D85: C3
        jnz     short 4DA2h                                    ;#4D86: 75 1A
        mov     ax, 3300h                                      ;#4D88: B8 00 33
        int     21h                                            ;#4D8B: CD 21
        mov     al, dl                                         ;#4D8D: 8A C2
        mov     dx, 449h                                       ;#4D8F: BA 49 04
        call    near 39EEh                                     ;#4D92: E8 59 EC
        mov     dx, 4A3h                                       ;#4D95: BA A3 04
        or      al, al                                         ;#4D98: 0A C0
        jnz     short 4D9Fh                                    ;#4D9A: 75 03
        mov     dx, 48Ch                                       ;#4D9C: BA 8C 04
        jmp     near 39EEh                                     ;#4D9F: E9 4C EC
        mov     dx, 3D0h                                       ;#4DA2: BA D0 03
        jmp     near 2EE9h                                     ;#4DA5: E9 41 E1
        call    near 4E4Fh                                     ;#4DA8: E8 A4 00
        jcxz    4DB4h                                          ;#4DAB: E3 07
        mov     al, cl                                         ;#4DAD: 8A C1
        mov     ah, 2Eh                                        ;#4DAF: B4 2E
        int     21h                                            ;#4DB1: CD 21
        ret                                                    ;#4DB3: C3
        jnz     short 4DA2h                                    ;#4DB4: 75 EC
        mov     ah, 54h                                        ;#4DB6: B4 54
        int     21h                                            ;#4DB8: CD 21
        mov     dx, 451h                                       ;#4DBA: BA 51 04
        jmp     short 4D92h                                    ;#4DBD: EB D3
        call    near 4E4Fh                                     ;#4DBF: E8 8D 00
        jcxz    4DE7h                                          ;#4DC2: E3 23
        mov     dx, 0FFFFh                                     ;#4DC4: BA FF FF
        mov     ax, 3837h                                      ;#4DC7: B8 37 38
        or      cl, cl                                         ;#4DCA: 0A C9
        jnz     short 4DD0h                                    ;#4DCC: 75 02
        mov     al, 1                                          ;#4DCE: B0 01
        int     21h                                            ;#4DD0: CD 21
        jb      short 4DD5h                                    ;#4DD2: 72 01
        ret                                                    ;#4DD4: C3
        mov     ax, 1815h                                      ;#4DD5: B8 15 18
        int     21h                                            ;#4DD8: CD 21
        mov     dx, 3FDh                                       ;#4DDA: BA FD 03
        or      al, al                                         ;#4DDD: 0A C0
        jz      short 4DE4h                                    ;#4DDF: 74 03
        mov     dx, 429h                                       ;#4DE1: BA 29 04
        jmp     near 2EE9h                                     ;#4DE4: E9 02 E1
        jnz     short 4DA2h                                    ;#4DE7: 75 B9
        mov     dx, 4E1Bh                                      ;#4DE9: BA 1B 4E
        mov     ax, 3800h                                      ;#4DEC: B8 00 38
        int     21h                                            ;#4DEF: CD 21
        mov     al, 1                                          ;#4DF1: B0 01
        cmp     bx, 37h                                        ;#4DF3: 83 FB 37
        jz      short 4DFAh                                    ;#4DF6: 74 02
        xor     al, al                                         ;#4DF8: 32 C0
        mov     dx, 461h                                       ;#4DFA: BA 61 04
        jmp     short 4D92h                                    ;#4DFD: EB 93
        call    near 4E4Fh                                     ;#4DFF: E8 4D 00
        jcxz    4E13h                                          ;#4E02: E3 0F
        mov     dl, cl                                         ;#4E04: 8A D1
        inc     dl                                             ;#4E06: FE C2
        not     dl                                             ;#4E08: F6 D2
        and     dl, 3                                          ;#4E0A: 80 E2 03
        mov     ax, 1817h                                      ;#4E0D: B8 17 18
        int     21h                                            ;#4E10: CD 21
        ret                                                    ;#4E12: C3
        jnz     short 4DA2h                                    ;#4E13: 75 8D
        xor     dl, dl                                         ;#4E15: 32 D2
        mov     ax, 1817h                                      ;#4E17: B8 17 18
        int     21h                                            ;#4E1A: CD 21
        mov     dx, 46Bh                                       ;#4E1C: BA 6B 04
        jmp     near 4D92h                                     ;#4E1F: E9 70 FF
        mov     dx, 771h                                       ;#4E22: BA 71 07
        jmp     near 2EE9h                                     ;#4E25: E9 C1 E0
        call    near 4E4Fh                                     ;#4E28: E8 24 00
        jcxz    4E3Dh                                          ;#4E2B: E3 10
        mov     dl, cl                                         ;#4E2D: 8A D1
        not     dl                                             ;#4E2F: F6 D2
        and     dl, 1                                          ;#4E31: 80 E2 01
        add     dl, 3                                          ;#4E34: 80 C2 03
        mov     ax, 1816h                                      ;#4E37: B8 16 18
        int     21h                                            ;#4E3A: CD 21
        ret                                                    ;#4E3C: C3
        jnz     short 4E4Ch                                    ;#4E3D: 75 0D
        xor     dl, dl                                         ;#4E3F: 32 D2
        mov     ax, 1816h                                      ;#4E41: B8 16 18
        int     21h                                            ;#4E44: CD 21
        mov     dx, 475h                                       ;#4E46: BA 75 04
        jmp     near 4D92h                                     ;#4E49: E9 46 FF
        jmp     near 4DA2h                                     ;#4E4C: E9 53 FF
        call    near 301Fh                                     ;#4E4F: E8 CD E1
        cmp     byte [bp], 3Dh                                 ;#4E52: 80 7E 00 3D
        jnz     short 4E5Bh                                    ;#4E56: 75 03
        call    near 301Eh                                     ;#4E58: E8 C3 E1
        mov     si, bp                                         ;#4E5B: 8B F5
        mov     di, 0C5Bh                                      ;#4E5D: BF 5B 0C
        call    near 3140h                                     ;#4E60: E8 DD E2
        mov     bp, si                                         ;#4E63: 8B EE
        call    near 301Fh                                     ;#4E65: E8 B7 E1
        jz      short 4E6Dh                                    ;#4E68: 74 03
        mov     cx, 0                                          ;#4E6A: B9 00 00
        ret                                                    ;#4E6D: C3
        mov     si, bp                                         ;#4E6E: 8B F5
        lodsb                                                  ;#4E70: AC
        call    near 300Fh                                     ;#4E71: E8 9B E1
        jz      short 4E70h                                    ;#4E74: 74 FA
        cmp     al, 0Dh                                        ;#4E76: 3C 0D
        jz      short 4EC6h                                    ;#4E78: 74 4C
        dec     si                                             ;#4E7A: 4E
        mov     di, 81h                                        ;#4E7B: BF 81 00
        call    near 312Ah                                     ;#4E7E: E8 A9 E2
        mov     si, 81h                                        ;#4E81: BE 81 00
        lodsb                                                  ;#4E84: AC
        cmp     al, 0Dh                                        ;#4E85: 3C 0D
        jz      short 4E9Eh                                    ;#4E87: 74 15
        call    near 300Bh                                     ;#4E89: E8 7F E1
        jnz     short 4E84h                                    ;#4E8C: 75 F6
        mov     byte [si-1], 3Bh                               ;#4E8E: C6 44 FF 3B
        mov     di, si                                         ;#4E92: 8B FE
        push    si                                             ;#4E94: 56
        call    near 302Ah                                     ;#4E95: E8 92 E1
        call    near 312Ah                                     ;#4E98: E8 8F E2
        pop     si                                             ;#4E9B: 5E
        jmp     short 4E84h                                    ;#4E9C: EB E6
        mov     si, 51Dh                                       ;#4E9E: BE 1D 05
        mov     cx, 5                                          ;#4EA1: B9 05 00
        call    near 30F4h                                     ;#4EA4: E8 4D E2
        cmp     byte [81h], 3Bh                                ;#4EA7: 80 3E 81 00 3B
        jz      short 4EC5h                                    ;#4EAC: 74 17
        call    near 4FD5h                                     ;#4EAE: E8 24 01
        jb      short 4EE4h                                    ;#4EB1: 72 31
        mov     si, 51Dh                                       ;#4EB3: BE 1D 05
        mov     cx, 5                                          ;#4EB6: B9 05 00
        rep     movsb                                          ;#4EB9: F3 A4
        mov     si, 81h                                        ;#4EBB: BE 81 00
        call    near 2F78h                                     ;#4EBE: E8 B7 E0
        xor     ax, ax                                         ;#4EC1: 33 C0
        dec     di                                             ;#4EC3: 4F
        stosw                                                  ;#4EC4: AB
        ret                                                    ;#4EC5: C3
        mov     si, 51Dh                                       ;#4EC6: BE 1D 05
        mov     cx, 5                                          ;#4EC9: B9 05 00
        call    near 311Ch                                     ;#4ECC: E8 4D E2
        jb      short 4EDEh                                    ;#4ECF: 72 0D
        call    near 3AFEh                                     ;#4ED1: E8 2A EC
        push    es                                             ;#4ED4: 06
        pop     ds                                             ;#4ED5: 1F
        mov     dx, di                                         ;#4ED6: 8B D7
        call    near 39E4h                                     ;#4ED8: E8 09 EB
        jmp     near 3AD6h                                     ;#4EDB: E9 F8 EB
        mov     dx, 500h                                       ;#4EDE: BA 00 05
        jmp     near 39EEh                                     ;#4EE1: E9 0A EB
        mov     dx, 4DBh                                       ;#4EE4: BA DB 04
        jmp     near 2EE9h                                     ;#4EE7: E9 FF DF
        call    near 301Fh                                     ;#4EEA: E8 32 E1
        cmp     byte [bp], 3Dh                                 ;#4EED: 80 7E 00 3D
        jnz     short 4EF6h                                    ;#4EF1: 75 03
        call    near 301Eh                                     ;#4EF3: E8 28 E1
        mov     si, bp                                         ;#4EF6: 8B F5
        mov     di, 81h                                        ;#4EF8: BF 81 00
        call    near 312Ah                                     ;#4EFB: E8 2C E2
        mov     si, 522h                                       ;#4EFE: BE 22 05
        mov     cx, 7                                          ;#4F01: B9 07 00
        call    near 30F4h                                     ;#4F04: E8 ED E1
        cmp     byte [81h], 0Dh                                ;#4F07: 80 3E 81 00 0D
        jz      short 4F25h                                    ;#4F0C: 74 17
        call    near 4FD5h                                     ;#4F0E: E8 C4 00
        jb      short 4EE4h                                    ;#4F11: 72 D1
        mov     si, 522h                                       ;#4F13: BE 22 05
        mov     cx, 7                                          ;#4F16: B9 07 00
        rep     movsb                                          ;#4F19: F3 A4
        mov     si, 81h                                        ;#4F1B: BE 81 00
        call    near 2F94h                                     ;#4F1E: E8 73 E0
        xor     ax, ax                                         ;#4F21: 33 C0
        dec     di                                             ;#4F23: 4F
        stosw                                                  ;#4F24: AB
        ret                                                    ;#4F25: C3
        mov     ax, 204h                                       ;#4F26: B8 04 02
        call    near 31F2h                                     ;#4F29: E8 C6 E2
        jb      short 4FA5h                                    ;#4F2C: 72 77
        mov     [49C3h], ax                                    ;#4F2E: A3 C3 49
        mov     si, bp                                         ;#4F31: 8B F5
        mov     di, 81h                                        ;#4F33: BF 81 00
        call    near 312Ah                                     ;#4F36: E8 F1 E1
        mov     si, 81h                                        ;#4F39: BE 81 00
        cmp     byte [si], 0Dh                                 ;#4F3C: 80 3C 0D
        jz      short 4FB4h                                    ;#4F3F: 74 73
        cmp     byte [si], 3Dh                                 ;#4F41: 80 3C 3D
        jz      short 4FABh                                    ;#4F44: 74 65
        lodsb                                                  ;#4F46: AC
        call    near 2F00h                                     ;#4F47: E8 B6 DF
        mov     [si-1], al                                     ;#4F4A: 88 44 FF
        cmp     al, 0Dh                                        ;#4F4D: 3C 0D
        jz      short 4FABh                                    ;#4F4F: 74 5A
        cmp     al, 3Dh                                        ;#4F51: 3C 3D
        jnz     short 4F46h                                    ;#4F53: 75 F1
        lea     cx, [si+0FF7Fh]                                ;#4F55: 8D 8C 7F FF
        cmp     byte [si], 0Dh                                 ;#4F59: 80 3C 0D
        pushf                                                  ;#4F5C: 9C
        mov     si, 81h                                        ;#4F5D: BE 81 00
        call    near 30F4h                                     ;#4F60: E8 91 E1
        popf                                                   ;#4F63: 9D
        jz      short 4F85h                                    ;#4F64: 74 1F
        xor     bp, bp                                         ;#4F66: 33 ED
        call    near 4FD5h                                     ;#4F68: E8 6A 00
        jb      short 4FB1h                                    ;#4F6B: 72 44
        mov     si, 81h                                        ;#4F6D: BE 81 00
        test    word [49C3h], 4                                ;#4F70: F7 06 C3 49 04 00
        lodsb                                                  ;#4F76: AC
        jz      short 4F7Ch                                    ;#4F77: 74 03
        call    near 2F00h                                     ;#4F79: E8 84 DF
        stosb                                                  ;#4F7C: AA
        cmp     al, 0Dh                                        ;#4F7D: 3C 0D
        jnz     short 4F70h                                    ;#4F7F: 75 EF
        xor     ax, ax                                         ;#4F81: 33 C0
        dec     di                                             ;#4F83: 4F
        stosw                                                  ;#4F84: AB
        test    word [cs:49C3h], 200h                          ;#4F85: 2E F7 06 C3 49 00 02
        jz      short 4FA4h                                    ;#4F8C: 74 16
        push    es                                             ;#4F8E: 06
        pop     ds                                             ;#4F8F: 1F
        xor     si, si                                         ;#4F90: 33 F6
        call    near 3135h                                     ;#4F92: E8 A0 E1
        jnz     short 4F92h                                    ;#4F95: 75 FB
        mov     bx, si                                         ;#4F97: 8B DE
        add     bx, 10h                                        ;#4F99: 83 C3 10
        mov     cl, 4                                          ;#4F9C: B1 04
        shr     bx, cl                                         ;#4F9E: D3 EB
        mov     ah, 4Ah                                        ;#4FA0: B4 4A
        int     21h                                            ;#4FA2: CD 21
        ret                                                    ;#4FA4: C3
        mov     dx, 184h                                       ;#4FA5: BA 84 01
        jmp     near 2EE9h                                     ;#4FA8: E9 3E DF
        mov     dx, 4B7h                                       ;#4FAB: BA B7 04
        jmp     near 2EE9h                                     ;#4FAE: E9 38 DF
        jmp     near 4EE4h                                     ;#4FB1: E9 30 FF
        mov     ds, [4660h]                                    ;#4FB4: 8E 1E 60 46
        mov     ds, [2Ch]                                      ;#4FB8: 8E 1E 2C 00
        push    ds                                             ;#4FBC: 1E
        pop     es                                             ;#4FBD: 07
        xor     si, si                                         ;#4FBE: 33 F6
        cmp     byte [si], 0                                   ;#4FC0: 80 3C 00
        jz      short 4F85h                                    ;#4FC3: 74 C0
        call    near 3AFEh                                     ;#4FC5: E8 36 EB
        mov     dx, si                                         ;#4FC8: 8B D6
        call    near 39E4h                                     ;#4FCA: E8 17 EA
        call    near 3AD6h                                     ;#4FCD: E8 06 EB
        call    near 3135h                                     ;#4FD0: E8 62 E1
        jmp     short 4FC3h                                    ;#4FD3: EB EE
        mov     ax, es                                         ;#4FD5: 8C C0
        dec     ax                                             ;#4FD7: 48
        push    ds                                             ;#4FD8: 1E
        mov     ds, ax                                         ;#4FD9: 8E D8
        mov     ax, [3]                                        ;#4FDB: A1 03 00
        pop     ds                                             ;#4FDE: 1F
        mov     cl, 4                                          ;#4FDF: B1 04
        shl     ax, cl                                         ;#4FE1: D3 E0
        mov     bx, ax                                         ;#4FE3: 8B D8
        sub     ax, di                                         ;#4FE5: 2B C7
        push    ax                                             ;#4FE7: 50
        mov     si, 81h                                        ;#4FE8: BE 81 00
        mov     ah, 0Dh                                        ;#4FEB: B4 0D
        call    near 3137h                                     ;#4FED: E8 47 E1
        lea     si, [bp+si+0FF7Fh]                             ;#4FF0: 8D B2 7F FF
        pop     ax                                             ;#4FF4: 58
        sub     si, ax                                         ;#4FF5: 2B F0
        cmc                                                    ;#4FF7: F5
        jnb     short 503Eh                                    ;#4FF8: 73 44
        lea     bx, [bx+si+10h]                                ;#4FFA: 8D 58 10
        shr     bx, cl                                         ;#4FFD: D3 EB
        call    near 3064h                                     ;#4FFF: E8 62 E0
        push    bx                                             ;#5002: 53
        mov     ah, 4Ah                                        ;#5003: B4 4A
        int     21h                                            ;#5005: CD 21
        pop     bx                                             ;#5007: 5B
        jnb     short 502Dh                                    ;#5008: 73 23
        mov     ah, 48h                                        ;#500A: B4 48
        int     21h                                            ;#500C: CD 21
        jb      short 502Dh                                    ;#500E: 72 1D
        push    ax                                             ;#5010: 50
        push    es                                             ;#5011: 06
        pop     ds                                             ;#5012: 1F
        mov     es, ax                                         ;#5013: 8E C0
        mov     cl, 3                                          ;#5015: B1 03
        shl     bx, cl                                         ;#5017: D3 E3
        mov     cx, bx                                         ;#5019: 8B CB
        xor     si, si                                         ;#501B: 33 F6
        push    di                                             ;#501D: 57
        xor     di, di                                         ;#501E: 33 FF
        rep     movsw                                          ;#5020: F3 A5
        pop     di                                             ;#5022: 5F
        push    ds                                             ;#5023: 1E
        pop     es                                             ;#5024: 07
        mov     ah, 49h                                        ;#5025: B4 49
        int     21h                                            ;#5027: CD 21
        pop     es                                             ;#5029: 07
        push    cs                                             ;#502A: 0E
        pop     ds                                             ;#502B: 1F
        clc                                                    ;#502C: F8
        pushf                                                  ;#502D: 9C
        push    es                                             ;#502E: 06
        mov     ax, es                                         ;#502F: 8C C0
        mov     es, [4660h]                                    ;#5031: 8E 06 60 46
        mov     [es:2Ch], ax                                   ;#5035: 26 A3 2C 00
        call    near 3079h                                     ;#5039: E8 3D E0
        pop     es                                             ;#503C: 07
        popf                                                   ;#503D: 9D
        ret                                                    ;#503E: C3
        mov     ds, [cs:4660h]                                 ;#503F: 2E 8E 1E 60 46
        jmp     far word [291h]                                ;#5044: FF 2E 91 02
        mov     ds, [cs:4660h]                                 ;#5048: 2E 8E 1E 60 46
        and     byte [339h], 0F8h                              ;#504D: 80 26 39 03 F8
        jmp     far word [295h]                                ;#5052: FF 2E 95 02
        mov     al, 7                                          ;#5056: B0 07
        jmp     near 3AE9h                                     ;#5058: E9 8E EA
        mov     dx, 5C7h                                       ;#505B: BA C7 05
        call    near 39EEh                                     ;#505E: E8 8D E9
        mov     ax, 0C08h                                      ;#5061: B8 08 0C
        int     21h                                            ;#5064: CD 21
        mov     ax, 0C00h                                      ;#5066: B8 00 0C
        int     21h                                            ;#5069: CD 21
        mov     dx, 52Eh                                       ;#506B: BA 2E 05
        jmp     near 39EEh                                     ;#506E: E9 7D E9
        mov     dx, 5C7h                                       ;#5071: BA C7 05
        call    near 39FDh                                     ;#5074: E8 86 E9
        mov     ax, 0C08h                                      ;#5077: B8 08 0C
        int     21h                                            ;#507A: CD 21
        mov     ax, 0C00h                                      ;#507C: B8 00 0C
        int     21h                                            ;#507F: CD 21
        mov     dx, 52Eh                                       ;#5081: BA 2E 05
        jmp     near 39FDh                                     ;#5084: E9 76 E9
        mov     ds, [4660h]                                    ;#5087: 8E 1E 60 46
        call    near 3AD6h                                     ;#508B: E8 48 EA
        mov     dx, MSG_SISNE_PLUS                             ;#508E: BA 26 0B
        call    near 39EEh                                     ;#5091: E8 5A E9
        call    near 3AD6h                                     ;#5094: E8 3F EA
        mov     dx, 0B48h                                      ;#5097: BA 48 0B
        call    near 39EEh                                     ;#509A: E8 51 E9
        jmp     near 3AD6h                                     ;#509D: E9 36 EA
        call    near 301Fh                                     ;#50A0: E8 7C DF
        mov     di, 478Ah                                      ;#50A3: BF 8A 47
        call    near 330Ah                                     ;#50A6: E8 61 E2
        jb      short 50C2h                                    ;#50A9: 72 17
        call    near 301Fh                                     ;#50AB: E8 71 DF
        mov     dx, 15Ch                                       ;#50AE: BA 5C 01
        jnz     short 50C5h                                    ;#50B1: 75 12
        mov     dx, 478Ah                                      ;#50B3: BA 8A 47
        mov     es, [4660h]                                    ;#50B6: 8E 06 60 46
        call    far word [es:29Dh]                             ;#50BA: 26 FF 1E 9D 02
        jb      short 50C2h                                    ;#50BF: 72 01
        ret                                                    ;#50C1: C3
        mov     dx, 5EAh                                       ;#50C2: BA EA 05
        jmp     near 2EE9h                                     ;#50C5: E9 21 DE
        mov     byte [4E63h], 0                                ;#50C8: C6 06 63 4E 00
        mov     di, 0C2Dh                                      ;#50CD: BF 2D 0C
        mov     ax, 50h                                        ;#50D0: B8 50 00
        call    near 31A4h                                     ;#50D3: E8 CE E0
        jb      short 510Dh                                    ;#50D6: 72 35
        mov     [49BEh], ax                                    ;#50D8: A3 BE 49
        mov     bl, 7                                          ;#50DB: B3 07
        call    near 5209h                                     ;#50DD: E8 29 01
        jb      short 510Dh                                    ;#50E0: 72 2B
        mov     [49C0h], bl                                    ;#50E2: 88 1E C0 49
        mov     bl, 0                                          ;#50E6: B3 00
        call    near 5209h                                     ;#50E8: E8 1E 01
        jb      short 510Dh                                    ;#50EB: 72 20
        mov     [49C1h], bl                                    ;#50ED: 88 1E C1 49
        call    near 5209h                                     ;#50F1: E8 15 01
        jb      short 510Dh                                    ;#50F4: 72 17
        mov     [49C2h], bl                                    ;#50F6: 88 1E C2 49
        mov     di, 0C2Dh                                      ;#50FA: BF 2D 0C
        mov     ax, 50h                                        ;#50FD: B8 50 00
        call    near 31A4h                                     ;#5100: E8 A1 E0
        jb      short 510Dh                                    ;#5103: 72 08
        jnz     short 5112h                                    ;#5105: 75 0B
        or      [49BEh], ax                                    ;#5107: 09 06 BE 49
        jmp     short 5118h                                    ;#510B: EB 0B
        mov     dx, 184h                                       ;#510D: BA 84 01
        jmp     short 5115h                                    ;#5110: EB 03
        mov     dx, 15Ch                                       ;#5112: BA 5C 01
        jmp     near 2EE9h                                     ;#5115: E9 D1 DD
        mov     bx, 1                                          ;#5118: BB 01 00
        mov     ax, 4400h                                      ;#511B: B8 00 44
        int     21h                                            ;#511E: CD 21
        not     dl                                             ;#5120: F6 D2
        test    dl, 82h                                        ;#5122: F6 C2 82
        jnz     short 5197h                                    ;#5125: 75 70
        push    es                                             ;#5127: 06
        mov     ax, 3529h                                      ;#5128: B8 29 35
        int     21h                                            ;#512B: CD 21
        mov     ax, es                                         ;#512D: 8C C0
        pop     es                                             ;#512F: 07
        cmp     ax, 70h                                        ;#5130: 3D 70 00
        jnbe    short 5197h                                    ;#5133: 77 62
        mov     ah, 0Fh                                        ;#5135: B4 0F
        int     10h                                            ;#5137: CD 10
        push    ax                                             ;#5139: 50
        xor     dx, dx                                         ;#513A: 33 D2
        mov     ah, 2                                          ;#513C: B4 02
        int     10h                                            ;#513E: CD 10
        pop     ax                                             ;#5140: 58
        mov     dl, ah                                         ;#5141: 8A D4
        dec     dl                                             ;#5143: FE CA
        mov     bl, [49C0h]                                    ;#5145: 8A 1E C0 49
        test    word [49BEh], 10h                              ;#5149: F7 06 BE 49 10 00
        jz      short 5159h                                    ;#514F: 74 08
        mov     byte [4E63h], 1                                ;#5151: C6 06 63 4E 01
        or      bl, 8                                          ;#5156: 80 CB 08
        mov     bh, [49C1h]                                    ;#5159: 8A 3E C1 49
        test    word [49BEh], 40h                              ;#515D: F7 06 BE 49 40 00
        jz      short 516Dh                                    ;#5163: 74 08
        mov     byte [4E63h], 1                                ;#5165: C6 06 63 4E 01
        or      bh, 8                                          ;#516A: 80 CF 08
        cmp     al, 3                                          ;#516D: 3C 03
        jbe     short 5185h                                    ;#516F: 76 14
        cmp     al, 7                                          ;#5171: 3C 07
        jz      short 5185h                                    ;#5173: 74 10
        cmp     byte [4E63h], 1                                ;#5175: 80 3E 63 4E 01
        jz      short 5181h                                    ;#517A: 74 05
        mov     ah, 0                                          ;#517C: B4 00
        int     10h                                            ;#517E: CD 10
        ret                                                    ;#5180: C3
        mov     dh, 32h                                        ;#5181: B6 32
        jmp     short 5187h                                    ;#5183: EB 02
        mov     dh, 18h                                        ;#5185: B6 18
        mov     cl, 4                                          ;#5187: B1 04
        shl     bh, cl                                         ;#5189: D2 E7
        or      bh, bl                                         ;#518B: 0A FB
        xor     ax, ax                                         ;#518D: 33 C0
        mov     cx, ax                                         ;#518F: 8B C8
        mov     ah, 6                                          ;#5191: B4 06
        int     10h                                            ;#5193: CD 10
        jmp     short 51F2h                                    ;#5195: EB 5B
        mov     dx, 54Ah                                       ;#5197: BA 4A 05
        mov     ah, 9                                          ;#519A: B4 09
        int     21h                                            ;#519C: CD 21
        test    word [49BEh], 10h                              ;#519E: F7 06 BE 49 10 00
        jz      short 51ADh                                    ;#51A4: 74 07
        mov     dx, 54Fh                                       ;#51A6: BA 4F 05
        mov     ah, 9                                          ;#51A9: B4 09
        int     21h                                            ;#51AB: CD 21
        test    word [49BEh], 40h                              ;#51AD: F7 06 BE 49 40 00
        jz      short 51BCh                                    ;#51B3: 74 07
        mov     dx, 554h                                       ;#51B5: BA 54 05
        mov     ah, 9                                          ;#51B8: B4 09
        int     21h                                            ;#51BA: CD 21
        mov     dx, 541h                                       ;#51BC: BA 41 05
        mov     ah, 9                                          ;#51BF: B4 09
        int     21h                                            ;#51C1: CD 21
        xor     bh, bh                                         ;#51C3: 32 FF
        mov     bl, [49C0h]                                    ;#51C5: 8A 1E C0 49
        mov     dl, [bx+534h]                                  ;#51C9: 8A 97 34 05
        mov     ah, 2                                          ;#51CD: B4 02
        int     21h                                            ;#51CF: CD 21
        mov     dx, 545h                                       ;#51D1: BA 45 05
        mov     ah, 9                                          ;#51D4: B4 09
        int     21h                                            ;#51D6: CD 21
        mov     bl, [49C1h]                                    ;#51D8: 8A 1E C1 49
        mov     dl, [bx+534h]                                  ;#51DC: 8A 97 34 05
        mov     ah, 2                                          ;#51E0: B4 02
        int     21h                                            ;#51E2: CD 21
        mov     dx, 548h                                       ;#51E4: BA 48 05
        mov     ah, 9                                          ;#51E7: B4 09
        int     21h                                            ;#51E9: CD 21
        mov     dx, 53Ch                                       ;#51EB: BA 3C 05
        mov     ah, 9                                          ;#51EE: B4 09
        int     21h                                            ;#51F0: CD 21
        mov     ah, 0Fh                                        ;#51F2: B4 0F
        int     10h                                            ;#51F4: CD 10
        cmp     al, 4                                          ;#51F6: 3C 04
        jb      short 51FEh                                    ;#51F8: 72 04
        cmp     al, 7                                          ;#51FA: 3C 07
        jnz     short 5208h                                    ;#51FC: 75 0A
        mov     ah, 0Bh                                        ;#51FE: B4 0B
        xor     bh, bh                                         ;#5200: 32 FF
        mov     bl, [49C2h]                                    ;#5202: 8A 1E C2 49
        int     10h                                            ;#5206: CD 10
        ret                                                    ;#5208: C3
        call    near 2F0Bh                                     ;#5209: E8 FF DC
        jz      short 5237h                                    ;#520C: 74 29
        cmp     [cs:4662h], al                                 ;#520E: 2E 38 06 62 46
        jz      short 5237h                                    ;#5213: 74 22
        cmp     al, 2Ch                                        ;#5215: 3C 2C
        jz      short 5236h                                    ;#5217: 74 1D
        xchg    si, bp                                         ;#5219: 87 EE
        mov     ah, 4                                          ;#521B: B4 04
        call    near 322Bh                                     ;#521D: E8 0B E0
        xchg    bp, si                                         ;#5220: 87 F5
        jb      short 5238h                                    ;#5222: 72 14
        mov     bx, dx                                         ;#5224: 8B DA
        and     bx, 7                                          ;#5226: 81 E3 07 00
        mov     byte [4E63h], 1                                ;#522A: C6 06 63 4E 01
        call    near 2F0Bh                                     ;#522F: E8 D9 DC
        cmp     al, 2Ch                                        ;#5232: 3C 2C
        jnz     short 5237h                                    ;#5234: 75 01
        inc     si                                             ;#5236: 46
        clc                                                    ;#5237: F8
        ret                                                    ;#5238: C3
        call    near 52C5h                                     ;#5239: E8 89 00
        jz      short 52B9h                                    ;#523C: 74 7B
        call    near 531Bh                                     ;#523E: E8 DA 00
        jb      short 52C2h                                    ;#5241: 72 7F
        jnz     short 5275h                                    ;#5243: 75 30
        mov     [485Bh], dl                                    ;#5245: 88 16 5B 48
        call    near 3229h                                     ;#5249: E8 DD DF
        jb      short 52BAh                                    ;#524C: 72 6C
        mov     [485Ch], dl                                    ;#524E: 88 16 5C 48
        call    near 537Fh                                     ;#5252: E8 2A 01
        jb      short 52BAh                                    ;#5255: 72 63
        mov     ah, 4                                          ;#5257: B4 04
        call    near 322Bh                                     ;#5259: E8 CF DF
        jb      short 52BAh                                    ;#525C: 72 5C
        cmp     dx, 64h                                        ;#525E: 83 FA 64
        jnb     short 5267h                                    ;#5261: 73 04
        add     dx, 76Ch                                       ;#5263: 81 C2 6C 07
        mov     [485Dh], dx                                    ;#5267: 89 16 5D 48
        mov     al, [bp]                                       ;#526B: 8A 46 00
        call    near 3000h                                     ;#526E: E8 8F DD
        jnz     short 52BAh                                    ;#5271: 75 47
        jmp     short 52AFh                                    ;#5273: EB 3A
        xchg    [485Fh], dl                                    ;#5275: 86 16 5F 48
        mov     bl, 3Ah                                        ;#5279: B3 3A
        call    near 538Fh                                     ;#527B: E8 11 01
        jb      short 52A7h                                    ;#527E: 72 27
        call    near 3229h                                     ;#5280: E8 A6 DF
        jb      short 52BFh                                    ;#5283: 72 3A
        xchg    [4860h], dl                                    ;#5285: 86 16 60 48
        call    near 538Fh                                     ;#5289: E8 03 01
        jb      short 52A7h                                    ;#528C: 72 19
        call    near 3229h                                     ;#528E: E8 98 DF
        jb      short 52BFh                                    ;#5291: 72 2C
        xchg    [4861h], dl                                    ;#5293: 86 16 61 48
        mov     bl, 2Eh                                        ;#5297: B3 2E
        call    near 538Fh                                     ;#5299: E8 F3 00
        jb      short 52A7h                                    ;#529C: 72 09
        call    near 3229h                                     ;#529E: E8 88 DF
        jb      short 52BFh                                    ;#52A1: 72 1C
        mov     [4862h], dl                                    ;#52A3: 88 16 62 48
        mov     al, [bp]                                       ;#52A7: 8A 46 00
        call    near 3000h                                     ;#52AA: E8 53 DD
        jnz     short 52BFh                                    ;#52AD: 75 10
        call    near 301Fh                                     ;#52AF: E8 6D DD
        jnz     short 523Eh                                    ;#52B2: 75 8A
        call    near 5340h                                     ;#52B4: E8 89 00
        jnz     short 52C2h                                    ;#52B7: 75 09
        ret                                                    ;#52B9: C3
        mov     dx, 609h                                       ;#52BA: BA 09 06
        jmp     short 52C2h                                    ;#52BD: EB 03
        mov     dx, 621h                                       ;#52BF: BA 21 06
        jmp     near 2EE9h                                     ;#52C2: E9 24 DC
        xor     ax, ax                                         ;#52C5: 33 C0
        mov     [485Ah], al                                    ;#52C7: A2 5A 48
        mov     [485Bh], al                                    ;#52CA: A2 5B 48
        mov     [485Ch], al                                    ;#52CD: A2 5C 48
        mov     [485Dh], ax                                    ;#52D0: A3 5D 48
        mov     [485Fh], al                                    ;#52D3: A2 5F 48
        mov     [4860h], al                                    ;#52D6: A2 60 48
        mov     [4861h], al                                    ;#52D9: A2 61 48
        mov     [4862h], al                                    ;#52DC: A2 62 48
        call    near 301Fh                                     ;#52DF: E8 3D DD
        jz      short 52EDh                                    ;#52E2: 74 09
        cmp     al, 3Dh                                        ;#52E4: 3C 3D
        jnz     short 531Ah                                    ;#52E6: 75 32
        call    near 301Eh                                     ;#52E8: E8 33 DD
        jnz     short 531Ah                                    ;#52EB: 75 2D
        call    near 3AFEh                                     ;#52ED: E8 0E E8
        call    near 3B5Ch                                     ;#52F0: E8 69 E8
        call    near 3AFEh                                     ;#52F3: E8 08 E8
        call    near 3B9Bh                                     ;#52F6: E8 A2 E8
        mov     byte [46E4h], 20h                              ;#52F9: C6 06 E4 46 20
        mov     word [46E5h], 0D00h                            ;#52FE: C7 06 E5 46 00 0D
        mov     dx, 639h                                       ;#5304: BA 39 06
        call    near 39EEh                                     ;#5307: E8 E4 E6
        mov     dx, 46E4h                                      ;#530A: BA E4 46
        mov     ah, 0Ah                                        ;#530D: B4 0A
        int     21h                                            ;#530F: CD 21
        call    near 3AD6h                                     ;#5311: E8 C2 E7
        mov     bp, 46E6h                                      ;#5314: BD E6 46
        call    near 301Fh                                     ;#5317: E8 05 DD
        ret                                                    ;#531A: C3
        call    near 3229h                                     ;#531B: E8 0B DF
        jb      short 5337h                                    ;#531E: 72 17
        call    near 537Fh                                     ;#5320: E8 5C 00
        mov     al, 1                                          ;#5323: B0 01
        jnb     short 5329h                                    ;#5325: 73 02
        mov     al, 2                                          ;#5327: B0 02
        test    [485Ah], al                                    ;#5329: 84 06 5A 48
        jnz     short 533Bh                                    ;#532D: 75 0C
        or      [485Ah], al                                    ;#532F: 08 06 5A 48
        dec     al                                             ;#5333: FE C8
        clc                                                    ;#5335: F8
        ret                                                    ;#5336: C3
        mov     dx, 4B7h                                       ;#5337: BA B7 04
        ret                                                    ;#533A: C3
        mov     dx, 15Ch                                       ;#533B: BA 5C 01
        stc                                                    ;#533E: F9
        ret                                                    ;#533F: C3
        test    byte [485Ah], 1                                ;#5340: F6 06 5A 48 01
        jz      short 535Eh                                    ;#5345: 74 17
        mov     dl, [485Bh]                                    ;#5347: 8A 16 5B 48
        mov     dh, [485Ch]                                    ;#534B: 8A 36 5C 48
        mov     cx, [485Dh]                                    ;#534F: 8B 0E 5D 48
        mov     ah, 2Bh                                        ;#5353: B4 2B
        int     21h                                            ;#5355: CD 21
        mov     dx, 609h                                       ;#5357: BA 09 06
        or      al, al                                         ;#535A: 0A C0
        jnz     short 537Eh                                    ;#535C: 75 20
        test    byte [485Ah], 2                                ;#535E: F6 06 5A 48 02
        jz      short 537Eh                                    ;#5363: 74 19
        mov     ch, [485Fh]                                    ;#5365: 8A 2E 5F 48
        mov     cl, [4860h]                                    ;#5369: 8A 0E 60 48
        mov     dh, [4861h]                                    ;#536D: 8A 36 61 48
        mov     dl, [4862h]                                    ;#5371: 8A 16 62 48
        mov     ah, 2Dh                                        ;#5375: B4 2D
        int     21h                                            ;#5377: CD 21
        mov     dx, 621h                                       ;#5379: BA 21 06
        or      al, al                                         ;#537C: 0A C0
        ret                                                    ;#537E: C3
        inc     bp                                             ;#537F: 45
        cmp     byte [bp-1], 2Dh                               ;#5380: 80 7E FF 2D
        jz      short 538Eh                                    ;#5384: 74 08
        cmp     byte [bp-1], 2Fh                               ;#5386: 80 7E FF 2F
        jz      short 538Eh                                    ;#538A: 74 02
        dec     bp                                             ;#538C: 4D
        stc                                                    ;#538D: F9
        ret                                                    ;#538E: C3
        inc     bp                                             ;#538F: 45
        cmp     [bp-1], bl                                     ;#5390: 38 5E FF
        jz      short 5397h                                    ;#5393: 74 02
        dec     bp                                             ;#5395: 4D
        stc                                                    ;#5396: F9
        ret                                                    ;#5397: C3
        mov     dx, 559h                                       ;#5398: BA 59 05
        mov     ah, 3Bh                                        ;#539B: B4 3B
        jmp     short 53B8h                                    ;#539D: EB 19
        mov     dx, 5A0h                                       ;#539F: BA A0 05
        mov     ah, 39h                                        ;#53A2: B4 39
        jmp     short 53B8h                                    ;#53A4: EB 12
        mov     dx, 576h                                       ;#53A6: BA 76 05
        mov     ah, 3Ah                                        ;#53A9: B4 3A
        jmp     short 53B8h                                    ;#53AB: EB 0B
        mov     dx, 15Ch                                       ;#53AD: BA 5C 01
        jmp     short 53B5h                                    ;#53B0: EB 03
        mov     dx, 141h                                       ;#53B2: BA 41 01
        jmp     near 2EE9h                                     ;#53B5: E9 31 DB
        push    dx                                             ;#53B8: 52
        push    ax                                             ;#53B9: 50
        call    near 301Fh                                     ;#53BA: E8 62 DC
        mov     di, 478Ah                                      ;#53BD: BF 8A 47
        call    near 330Ah                                     ;#53C0: E8 47 DF
        pop     ax                                             ;#53C3: 58
        pop     dx                                             ;#53C4: 5A
        jb      short 53ADh                                    ;#53C5: 72 E6
        call    near 301Fh                                     ;#53C7: E8 55 DC
        jnz     short 53ADh                                    ;#53CA: 75 E1
        mov     al, [472Dh]                                    ;#53CC: A0 2D 47
        test    al, 80h                                        ;#53CF: A8 80
        jnz     short 53B2h                                    ;#53D1: 75 DF
        test    al, 8                                          ;#53D3: A8 08
        jnz     short 53B5h                                    ;#53D5: 75 DE
        test    al, 6                                          ;#53D7: A8 06
        jnz     short 53E9h                                    ;#53D9: 75 0E
        cmp     ah, 3Bh                                        ;#53DB: 80 FC 3B
        jnz     short 53ADh                                    ;#53DE: 75 CD
        mov     si, 478Ah                                      ;#53E0: BE 8A 47
        call    near 3B43h                                     ;#53E3: E8 5D E7
        jmp     near 3AD6h                                     ;#53E6: E9 ED E6
        push    dx                                             ;#53E9: 52
        mov     dx, 478Ah                                      ;#53EA: BA 8A 47
        int     21h                                            ;#53ED: CD 21
        pop     dx                                             ;#53EF: 5A
        jb      short 53B5h                                    ;#53F0: 72 C3
        ret                                                    ;#53F2: C3
        mov     ax, 0B700h                                     ;#53F3: B8 00 B7
        int     2Fh                                            ;#53F6: CD 2F
        or      al, al                                         ;#53F8: 0A C0
        jnz     short 540Eh                                    ;#53FA: 75 12
        pop     ax                                             ;#53FC: 58
        ret                                                    ;#53FD: C3
        mov     dx, 719h                                       ;#53FE: BA 19 07
        jmp     short 540Bh                                    ;#5401: EB 08
        mov     dx, 184h                                       ;#5403: BA 84 01
        jmp     short 540Bh                                    ;#5406: EB 03
        mov     dx, 15Ch                                       ;#5408: BA 5C 01
        jmp     near 2EE9h                                     ;#540B: E9 DB DA
        cmp     bx, 31Eh                                       ;#540E: 81 FB 1E 03
        jnz     short 53FEh                                    ;#5412: 75 EA
        dec     cl                                             ;#5414: FE C9
        cmp     cx, 0                                          ;#5416: 83 F9 00
        jb      short 53FEh                                    ;#5419: 72 E3
        mov     ax, 0B703h                                     ;#541B: B8 03 B7
        int     2Fh                                            ;#541E: CD 2F
        inc     ah                                             ;#5420: FE C4
        jnz     short 53FEh                                    ;#5422: 75 DA
        mov     [4A9Ch], al                                    ;#5424: A2 9C 4A
        mov     si, bp                                         ;#5427: 8B F5
        mov     di, 0C2Dh                                      ;#5429: BF 2D 0C
        mov     ax, 181Dh                                      ;#542C: B8 1D 18
        call    near 31A4h                                     ;#542F: E8 72 DD
        jb      short 5403h                                    ;#5432: 72 CF
        or      ax, ax                                         ;#5434: 0B C0
        jz      short 545Bh                                    ;#5436: 74 23
        mov     [4A9Dh], ax                                    ;#5438: A3 9D 4A
        call    near 2F0Bh                                     ;#543B: E8 CD DA
        jnz     short 5408h                                    ;#543E: 75 C8
        mov     bl, [4A9Ch]                                    ;#5440: 8A 1E 9C 4A
        mov     ax, [4A9Dh]                                    ;#5444: A1 9D 4A
        call    near 5505h                                     ;#5447: E8 BB 00
        mov     ax, 0B704h                                     ;#544A: B8 04 B7
        int     2Fh                                            ;#544D: CD 2F
        test    word [4A9Dh], 10h                              ;#544F: F7 06 9D 4A 10 00
        jz      short 545Ah                                    ;#5455: 74 03
        call    near 5534h                                     ;#5457: E8 DA 00
        ret                                                    ;#545A: C3
        lodsb                                                  ;#545B: AC
        call    near 300Fh                                     ;#545C: E8 B0 DB
        jz      short 545Bh                                    ;#545F: 74 FA
        cmp     al, 0Dh                                        ;#5461: 3C 0D
        jz      short 54CFh                                    ;#5463: 74 6A
        dec     si                                             ;#5465: 4E
        mov     di, 81h                                        ;#5466: BF 81 00
        call    near 312Ah                                     ;#5469: E8 BE DC
        mov     si, 81h                                        ;#546C: BE 81 00
        lodsb                                                  ;#546F: AC
        cmp     al, 0Dh                                        ;#5470: 3C 0D
        jz      short 548Fh                                    ;#5472: 74 1B
        cmp     [4662h], al                                    ;#5474: 38 06 62 46
        jz      short 5408h                                    ;#5478: 74 8E
        call    near 300Bh                                     ;#547A: E8 8E DB
        jnz     short 546Fh                                    ;#547D: 75 F0
        mov     byte [si-1], 3Bh                               ;#547F: C6 44 FF 3B
        mov     di, si                                         ;#5483: 8B FE
        push    si                                             ;#5485: 56
        call    near 302Ah                                     ;#5486: E8 A1 DB
        call    near 312Ah                                     ;#5489: E8 9E DC
        pop     si                                             ;#548C: 5E
        jmp     short 546Fh                                    ;#548D: EB E0
        test    byte [4A9Ch], 80h                              ;#548F: F6 06 9C 4A 80
        jnz     short 54A7h                                    ;#5494: 75 11
        mov     si, 81h                                        ;#5496: BE 81 00
        cmp     byte [si], 3Bh                                 ;#5499: 80 3C 3B
        jnz     short 54A1h                                    ;#549C: 75 03
        mov     byte [si], 0                                   ;#549E: C6 04 00
        mov     ax, 0B702h                                     ;#54A1: B8 02 B7
        int     2Fh                                            ;#54A4: CD 2F
        ret                                                    ;#54A6: C3
        mov     si, 712h                                       ;#54A7: BE 12 07
        mov     cx, 7                                          ;#54AA: B9 07 00
        call    near 30F4h                                     ;#54AD: E8 44 DC
        cmp     byte [81h], 3Bh                                ;#54B0: 80 3E 81 00 3B
        jz      short 54CEh                                    ;#54B5: 74 17
        call    near 4FD5h                                     ;#54B7: E8 1B FB
        jb      short 54FFh                                    ;#54BA: 72 43
        mov     si, 712h                                       ;#54BC: BE 12 07
        mov     cx, 7                                          ;#54BF: B9 07 00
        rep     movsb                                          ;#54C2: F3 A4
        mov     si, 81h                                        ;#54C4: BE 81 00
        call    near 2F94h                                     ;#54C7: E8 CA DA
        xor     ax, ax                                         ;#54CA: 33 C0
        dec     di                                             ;#54CC: 4F
        stosw                                                  ;#54CD: AB
        ret                                                    ;#54CE: C3
        test    byte [4A9Ch], 80h                              ;#54CF: F6 06 9C 4A 80
        jnz     short 54E1h                                    ;#54D4: 75 0B
        mov     ax, 0B705h                                     ;#54D6: B8 05 B7
        int     2Fh                                            ;#54D9: CD 2F
        or      al, al                                         ;#54DB: 0A C0
        jnz     short 54F9h                                    ;#54DD: 75 1A
        jmp     short 54ECh                                    ;#54DF: EB 0B
        mov     si, 712h                                       ;#54E1: BE 12 07
        mov     cx, 7                                          ;#54E4: B9 07 00
        call    near 311Ch                                     ;#54E7: E8 32 DC
        jb      short 54F9h                                    ;#54EA: 72 0D
        call    near 3AFEh                                     ;#54EC: E8 0F E6
        push    es                                             ;#54EF: 06
        pop     ds                                             ;#54F0: 1F
        mov     dx, di                                         ;#54F1: 8B D7
        call    near 39E4h                                     ;#54F3: E8 EE E4
        jmp     near 3AD6h                                     ;#54F6: E9 DD E5
        mov     dx, 500h                                       ;#54F9: BA 00 05
        jmp     near 39EEh                                     ;#54FC: E9 EF E4
        mov     dx, 4DBh                                       ;#54FF: BA DB 04
        jmp     near 2EE9h                                     ;#5502: E9 E4 D9
        test    ax, 4                                          ;#5505: A9 04 00
        jz      short 5510h                                    ;#5508: 74 06
        and     bl, 7Dh                                        ;#550A: 80 E3 7D
        or      bl, 1                                          ;#550D: 80 CB 01
        test    ax, 800h                                       ;#5510: A9 00 08
        jz      short 5518h                                    ;#5513: 74 03
        or      bl, 80h                                        ;#5515: 80 CB 80
        test    ax, 1000h                                      ;#5518: A9 00 10
        jz      short 5520h                                    ;#551B: 74 03
        or      bl, 2                                          ;#551D: 80 CB 02
        test    ax, 1                                          ;#5520: A9 01 00
        jz      short 552Bh                                    ;#5523: 74 06
        and     bl, 0FBh                                       ;#5525: 80 E3 FB
        or      bl, 1                                          ;#5528: 80 CB 01
        test    ax, 8                                          ;#552B: A9 08 00
        jz      short 5533h                                    ;#552E: 74 03
        or      bl, 4                                          ;#5530: 80 CB 04
        ret                                                    ;#5533: C3
        mov     dx, 736h                                       ;#5534: BA 36 07
        mov     bh, 4                                          ;#5537: B7 04
        not     bl                                             ;#5539: F6 D3
        call    near 5551h                                     ;#553B: E8 13 00
        not     bl                                             ;#553E: F6 D3
        test    bh, bl                                         ;#5540: 84 DF
        jnz     short 5561h                                    ;#5542: 75 1D
        mov     dx, 73Fh                                       ;#5544: BA 3F 07
        mov     bh, 2                                          ;#5547: B7 02
        call    near 5551h                                     ;#5549: E8 05 00
        mov     dx, 748h                                       ;#554C: BA 48 07
        mov     bh, 80h                                        ;#554F: B7 80
        call    near 39EEh                                     ;#5551: E8 9A E4
        mov     dx, 751h                                       ;#5554: BA 51 07
        test    bh, bl                                         ;#5557: 84 DF
        jnz     short 555Eh                                    ;#5559: 75 03
        mov     dx, 760h                                       ;#555B: BA 60 07
        call    near 39EEh                                     ;#555E: E8 8D E4
        ret                                                    ;#5561: C3
        mov     bl, 0FFh                                       ;#5562: B3 FF
        inc     bl                                             ;#5564: FE C3
        cmp     bl, [4707h]                                    ;#5566: 3A 1E 07 47
        jnb     short 5590h                                    ;#556A: 73 24
        mov     dx, 4AA3h                                      ;#556C: BA A3 4A
        mov     ax, 180Bh                                      ;#556F: B8 0B 18
        int     21h                                            ;#5572: CD 21
        cmp     [4A9Fh], al                                    ;#5574: 38 06 9F 4A
        jnz     short 5564h                                    ;#5578: 75 EA
        call    near 3AFEh                                     ;#557A: E8 81 E5
        mov     al, bl                                         ;#557D: 8A C3
        call    near 3B09h                                     ;#557F: E8 87 E5
        call    near 3B12h                                     ;#5582: E8 8D E5
        mov     dx, 4AA3h                                      ;#5585: BA A3 4A
        call    near 39E4h                                     ;#5588: E8 59 E4
        call    near 3AD6h                                     ;#558B: E8 48 E5
        jmp     short 5564h                                    ;#558E: EB D4
        ret                                                    ;#5590: C3
        mov     dx, 4AA3h                                      ;#5591: BA A3 4A
        mov     bl, [4AA0h]                                    ;#5594: 8A 1E A0 4A
        mov     ax, 180Bh                                      ;#5598: B8 0B 18
        int     21h                                            ;#559B: CD 21
        cmp     [4A9Fh], al                                    ;#559D: 38 06 9F 4A
        stc                                                    ;#55A1: F9
        jnz     short 55AAh                                    ;#55A2: 75 06
        mov     ax, 180Ah                                      ;#55A4: B8 0A 18
        int     21h                                            ;#55A7: CD 21
        clc                                                    ;#55A9: F8
        ret                                                    ;#55AA: C3
        mov     di, 0C2Dh                                      ;#55AB: BF 2D 0C
        mov     ax, 8                                          ;#55AE: B8 08 00
        call    near 31A4h                                     ;#55B1: E8 F0 DB
        jb      short 55F3h                                    ;#55B4: 72 3D
        mov     [4AA1h], ax                                    ;#55B6: A3 A1 4A
        call    near 349Eh                                     ;#55B9: E8 E2 DE
        js      short 55FDh                                    ;#55BC: 78 3F
        jz      short 55F8h                                    ;#55BE: 74 38
        dec     ah                                             ;#55C0: FE CC
        mov     [4AA0h], ah                                    ;#55C2: 88 26 A0 4A
        mov     al, [si]                                       ;#55C6: 8A 04
        call    near 2F18h                                     ;#55C8: E8 4D D9
        jnb     short 55F8h                                    ;#55CB: 73 2B
        cmp     ah, [4706h]                                    ;#55CD: 3A 26 06 47
        jz      short 5607h                                    ;#55D1: 74 34
        call    near 2F0Bh                                     ;#55D3: E8 35 D9
        cmp     al, 3Dh                                        ;#55D6: 3C 3D
        jnz     short 55DBh                                    ;#55D8: 75 01
        inc     si                                             ;#55DA: 46
        mov     di, 0C2Dh                                      ;#55DB: BF 2D 0C
        mov     ax, 8                                          ;#55DE: B8 08 00
        call    near 31A4h                                     ;#55E1: E8 C0 DB
        jb      short 55F3h                                    ;#55E4: 72 0D
        or      [4AA1h], ax                                    ;#55E6: 09 06 A1 4A
        jz      short 560Ch                                    ;#55EA: 74 20
        call    near 2F0Bh                                     ;#55EC: E8 1C D9
        jnz     short 55F8h                                    ;#55EF: 75 07
        clc                                                    ;#55F1: F8
        ret                                                    ;#55F2: C3
        mov     dx, 184h                                       ;#55F3: BA 84 01
        jmp     short 560Ah                                    ;#55F6: EB 12
        mov     dx, 15Ch                                       ;#55F8: BA 5C 01
        jmp     short 560Ah                                    ;#55FB: EB 0D
        mov     dx, 141h                                       ;#55FD: BA 41 01
        jmp     short 560Ah                                    ;#5600: EB 08
        mov     dx, 6A1h                                       ;#5602: BA A1 06
        jmp     short 560Ah                                    ;#5605: EB 03
        mov     dx, 681h                                       ;#5607: BA 81 06
        stc                                                    ;#560A: F9
        ret                                                    ;#560B: C3
        mov     dx, 4AA3h                                      ;#560C: BA A3 4A
        mov     bl, [4AA0h]                                    ;#560F: 8A 1E A0 4A
        mov     ax, 180Bh                                      ;#5613: B8 0B 18
        int     21h                                            ;#5616: CD 21
        cmp     al, 1                                          ;#5618: 3C 01
        jz      short 55FDh                                    ;#561A: 74 E1
        cmp     al, 2                                          ;#561C: 3C 02
        jz      short 5607h                                    ;#561E: 74 E7
        mov     bl, [4AA0h]                                    ;#5620: 8A 1E A0 4A
        inc     bl                                             ;#5624: FE C3
        xor     dx, dx                                         ;#5626: 33 D2
        mov     ax, 4409h                                      ;#5628: B8 09 44
        int     21h                                            ;#562B: CD 21
        test    dx, 1000h                                      ;#562D: F7 C2 00 10
        jnz     short 5607h                                    ;#5631: 75 D4
        cmp     byte [4A9Fh], 2                                ;#5633: 80 3E 9F 4A 02
        jz      short 5642h                                    ;#5638: 74 08
        mov     al, [4AA0h]                                    ;#563A: A0 A0 4A
        call    near 32E9h                                     ;#563D: E8 A9 DC
        jnz     short 55FDh                                    ;#5640: 75 BB
        mov     ah, 63h                                        ;#5642: B4 63
        mov     di, 4AA3h                                      ;#5644: BF A3 4A
        call    near 34F6h                                     ;#5647: E8 AC DE
        call    near 2F0Bh                                     ;#564A: E8 BE D8
        jnz     short 55F8h                                    ;#564D: 75 A9
        or      ah, ah                                         ;#564F: 0A E4
        js      short 55FDh                                    ;#5651: 78 AA
        or      bh, bh                                         ;#5653: 0A FF
        jnz     short 5602h                                    ;#5655: 75 AB
        dec     ah                                             ;#5657: FE CC
        cmp     [4AA0h], ah                                    ;#5659: 38 26 A0 4A
        jz      short 5607h                                    ;#565D: 74 A8
        mov     bh, [4AFEh]                                    ;#565F: 8A 3E FE 4A
        test    bh, 80h                                        ;#5663: F6 C7 80
        jnz     short 5602h                                    ;#5666: 75 9A
        test    bh, 48h                                        ;#5668: F6 C7 48
        jnz     short 5602h                                    ;#566B: 75 95
        mov     bl, [4B02h]                                    ;#566D: 8A 1E 02 4B
        xor     dx, dx                                         ;#5671: 33 D2
        mov     ax, 4409h                                      ;#5673: B8 09 44
        int     21h                                            ;#5676: CD 21
        test    dx, 1000h                                      ;#5678: F7 C2 00 10
        jnz     short 5698h                                    ;#567C: 75 1A
        cmp     byte [4A9Fh], 2                                ;#567E: 80 3E 9F 4A 02
        jnz     short 5696h                                    ;#5683: 75 11
        lea     dx, [4B09h]                                    ;#5685: 8D 16 09 4B
        mov     bl, [4B02h]                                    ;#5689: 8A 1E 02 4B
        mov     ax, 180Bh                                      ;#568D: B8 0B 18
        int     21h                                            ;#5690: CD 21
        cmp     al, 2                                          ;#5692: 3C 02
        jz      short 5698h                                    ;#5694: 74 02
        clc                                                    ;#5696: F8
        ret                                                    ;#5697: C3
        jmp     near 5607h                                     ;#5698: E9 6C FF
        mov     si, bp                                         ;#569B: 8B F5
        mov     byte [4A9Fh], 1                                ;#569D: C6 06 9F 4A 01
        call    near 2F0Bh                                     ;#56A2: E8 66 D8
        jnz     short 56AAh                                    ;#56A5: 75 03
        jmp     near 5562h                                     ;#56A7: E9 B8 FE
        call    near 55ABh                                     ;#56AA: E8 FE FE
        jb      short 56F9h                                    ;#56AD: 72 4A
        test    word [4AA1h], 8                                ;#56AF: F7 06 A1 4A 08 00
        jz      short 56C0h                                    ;#56B5: 74 09
        call    near 5591h                                     ;#56B7: E8 D7 FE
        mov     dx, 6BCh                                       ;#56BA: BA BC 06
        jb      short 56F9h                                    ;#56BD: 72 3A
        ret                                                    ;#56BF: C3
        mov     dx, 6A1h                                       ;#56C0: BA A1 06
        mov     di, 4AA6h                                      ;#56C3: BF A6 4A
        mov     ax, 5Ch                                        ;#56C6: B8 5C 00
        cmp     [di], ah                                       ;#56C9: 38 25
        jz      short 56F9h                                    ;#56CB: 74 2C
        call    near 2FB8h                                     ;#56CD: E8 E8 D8
        jz      short 56F9h                                    ;#56D0: 74 27
        test    byte [4AFEh], 4                                ;#56D2: F6 06 FE 4A 04
        jz      short 56E5h                                    ;#56D7: 74 0C
        mov     dx, 4AA3h                                      ;#56D9: BA A3 4A
        mov     ah, 39h                                        ;#56DC: B4 39
        int     21h                                            ;#56DE: CD 21
        mov     dx, 5A0h                                       ;#56E0: BA A0 05
        jb      short 56F9h                                    ;#56E3: 72 14
        mov     dx, 4AA3h                                      ;#56E5: BA A3 4A
        mov     bl, [4AA0h]                                    ;#56E8: 8A 1E A0 4A
        mov     ax, 1809h                                      ;#56EC: B8 09 18
        int     21h                                            ;#56EF: CD 21
        mov     dx, 6EAh                                       ;#56F1: BA EA 06
        or      al, al                                         ;#56F4: 0A C0
        jnz     short 56F9h                                    ;#56F6: 75 01
        ret                                                    ;#56F8: C3
        jmp     near 2EE9h                                     ;#56F9: E9 ED D7
        mov     si, bp                                         ;#56FC: 8B F5
        mov     byte [4A9Fh], 2                                ;#56FE: C6 06 9F 4A 02
        call    near 2F0Bh                                     ;#5703: E8 05 D8
        jnz     short 570Bh                                    ;#5706: 75 03
        jmp     near 5562h                                     ;#5708: E9 57 FE
        call    near 55ABh                                     ;#570B: E8 9D FE
        jb      short 573Fh                                    ;#570E: 72 2F
        test    word [4AA1h], 8                                ;#5710: F7 06 A1 4A 08 00
        jz      short 5721h                                    ;#5716: 74 09
        call    near 5591h                                     ;#5718: E8 76 FE
        mov     dx, 6BCh                                       ;#571B: BA BC 06
        jb      short 573Fh                                    ;#571E: 72 1F
        ret                                                    ;#5720: C3
        test    byte [4AFEh], 4                                ;#5721: F6 06 FE 4A 04
        mov     dx, 6A1h                                       ;#5726: BA A1 06
        jnz     short 573Fh                                    ;#5729: 75 14
        mov     dx, 4AA3h                                      ;#572B: BA A3 4A
        mov     bl, [4AA0h]                                    ;#572E: 8A 1E A0 4A
        mov     ax, 180Ch                                      ;#5732: B8 0C 18
        int     21h                                            ;#5735: CD 21
        mov     dx, 6EAh                                       ;#5737: BA EA 06
        or      al, al                                         ;#573A: 0A C0
        jnz     short 573Fh                                    ;#573C: 75 01
        ret                                                    ;#573E: C3
        jmp     near 2EE9h                                     ;#573F: E9 A7 D7
        mov     dx, 771h                                       ;#5742: BA 71 07
        jmp     near 2EE9h                                     ;#5745: E9 A1 D7
        push    ds                                             ;#5748: 1E
        mov     ds, [4660h]                                    ;#5749: 8E 1E 60 46
        mov     byte [335h], 1                                 ;#574D: C6 06 35 03 01
        pop     ds                                             ;#5752: 1F
        call    near 301Fh                                     ;#5753: E8 C9 D8
        mov     di, 4664h                                      ;#5756: BF 64 46
        call    near 2F9Fh                                     ;#5759: E8 43 D8
        jmp     near 2EADh                                     ;#575C: E9 4E D7
        mov     ax, [4660h]                                    ;#575F: A1 60 46
        mov     ds, ax                                         ;#5762: 8E D8
        mov     es, ax                                         ;#5764: 8E C0
        test    byte [339h], 1                                 ;#5766: F6 06 39 03 01
        jz      short 578Ch                                    ;#576B: 74 1F
        mov     dx, 812h                                       ;#576D: BA 12 08
        cmp     byte [335h], 0                                 ;#5770: 80 3E 35 03 00
        jz      short 577Fh                                    ;#5775: 74 08
        call    near 3094h                                     ;#5777: E8 1A D9
        jnb     short 578Ch                                    ;#577A: 73 10
        mov     dx, 794h                                       ;#577C: BA 94 07
        jmp     near 2EE9h                                     ;#577F: E9 67 D7
        mov     dx, 7EAh                                       ;#5782: BA EA 07
        jmp     short 577Fh                                    ;#5785: EB F8
        mov     dx, 184h                                       ;#5787: BA 84 01
        jmp     short 577Fh                                    ;#578A: EB F3
        mov     ax, 81h                                        ;#578C: B8 81 00
        call    near 31F2h                                     ;#578F: E8 60 DA
        jb      short 5787h                                    ;#5792: 72 F3
        test    ax, 80h                                        ;#5794: A9 80 00
        mov     al, 0                                          ;#5797: B0 00
        jz      short 579Dh                                    ;#5799: 74 02
        mov     al, 10h                                        ;#579B: B0 10
        mov     [5F4h], al                                     ;#579D: A2 F4 05
        call    near 301Fh                                     ;#57A0: E8 7C D8
        cmp     al, 25h                                        ;#57A3: 3C 25
        jnz     short 5782h                                    ;#57A5: 75 DB
        inc     bp                                             ;#57A7: 45
        mov     al, [bp]                                       ;#57A8: 8A 46 00
        call    near 2FF6h                                     ;#57AB: E8 48 D8
        jz      short 5782h                                    ;#57AE: 74 D2
        call    near 300Bh                                     ;#57B0: E8 58 D8
        jz      short 5782h                                    ;#57B3: 74 CD
        mov     [5EFh], al                                     ;#57B5: A2 EF 05
        call    near 301Eh                                     ;#57B8: E8 63 D8
        cmp     al, 28h                                        ;#57BB: 3C 28
        jz      short 57D2h                                    ;#57BD: 74 13
        mov     ax, [bp]                                       ;#57BF: 8B 46 00
        and     ax, 0DFDFh                                     ;#57C2: 25 DF DF
        cmp     ax, 4E49h                                      ;#57C5: 3D 49 4E
        jnz     short 5782h                                    ;#57C8: 75 B8
        inc     bp                                             ;#57CA: 45
        call    near 301Eh                                     ;#57CB: E8 50 D8
        cmp     al, 28h                                        ;#57CE: 3C 28
        jnz     short 5782h                                    ;#57D0: 75 B0
        inc     bp                                             ;#57D2: 45
        mov     di, 56Eh                                       ;#57D3: BF 6E 05
        mov     [5F0h], di                                     ;#57D6: 89 3E F0 05
        mov     word [di], 0                                   ;#57DA: C7 05 00 00
        mov     al, [bp]                                       ;#57DE: 8A 46 00
        inc     bp                                             ;#57E1: 45
        call    near 582Fh                                     ;#57E2: E8 4A 00
        jz      short 57DEh                                    ;#57E5: 74 F7
        dec     bp                                             ;#57E7: 4D
        mov     al, [bp]                                       ;#57E8: 8A 46 00
        inc     bp                                             ;#57EB: 45
        cmp     al, 0Dh                                        ;#57EC: 3C 0D
        jz      short 5782h                                    ;#57EE: 74 92
        stosb                                                  ;#57F0: AA
        call    near 582Fh                                     ;#57F1: E8 3B 00
        jz      short 57FBh                                    ;#57F4: 74 05
        cmp     al, 29h                                        ;#57F6: 3C 29
        jnz     short 57E8h                                    ;#57F8: 75 EE
        stc                                                    ;#57FA: F9
        mov     al, 0                                          ;#57FB: B0 00
        mov     [di-1], al                                     ;#57FD: 88 45 FF
        jnb     short 57DEh                                    ;#5800: 73 DC
        stosb                                                  ;#5802: AA
        mov     [5F5h], al                                     ;#5803: A2 F5 05
        call    near 301Fh                                     ;#5806: E8 16 D8
        mov     ax, [bp]                                       ;#5809: 8B 46 00
        and     ax, 0DFDFh                                     ;#580C: 25 DF DF
        cmp     ax, 4F44h                                      ;#580F: 3D 44 4F
        jnz     short 581Dh                                    ;#5812: 75 09
        inc     bp                                             ;#5814: 45
        call    near 301Eh                                     ;#5815: E8 06 D8
        mov     di, 5EEh                                       ;#5818: BF EE 05
        jnz     short 5820h                                    ;#581B: 75 03
        jmp     near 5782h                                     ;#581D: E9 62 FF
        std                                                    ;#5820: FD
        call    near 2F9Fh                                     ;#5821: E8 7B D7
        cld                                                    ;#5824: FC
        mov     byte [di+1], 0                                 ;#5825: C6 45 01 00
        or      byte [339h], 1                                 ;#5829: 80 0E 39 03 01
        ret                                                    ;#582E: C3
        cmp     al, 20h                                        ;#582F: 3C 20
        jz      short 583Dh                                    ;#5831: 74 0A
        cmp     al, 9                                          ;#5833: 3C 09
        jz      short 583Dh                                    ;#5835: 74 06
        cmp     al, 2Ch                                        ;#5837: 3C 2C
        jz      short 583Dh                                    ;#5839: 74 02
        cmp     al, 3Bh                                        ;#583B: 3C 3B
        ret                                                    ;#583D: C3
        mov     byte [49C9h], 0                                ;#583E: C6 06 C9 49 00
        call    near 301Fh                                     ;#5843: E8 D9 D7
        jz      short 5875h                                    ;#5846: 74 2D
        call    near 587Bh                                     ;#5848: E8 30 00
        jb      short 5875h                                    ;#584B: 72 28
        jcxz    585Fh                                          ;#584D: E3 10
        call    near 58DBh                                     ;#584F: E8 89 00
        jb      short 5875h                                    ;#5852: 72 21
        jcxz    585Fh                                          ;#5854: E3 09
        call    near 593Bh                                     ;#5856: E8 E2 00
        jb      short 5875h                                    ;#5859: 72 1A
        jcxz    585Fh                                          ;#585B: E3 02
        jmp     short 5843h                                    ;#585D: EB E4
        call    near 301Fh                                     ;#585F: E8 BD D7
        jz      short 5875h                                    ;#5862: 74 11
        cmp     byte [49C9h], 0                                ;#5864: 80 3E C9 49 00
        jz      short 586Ch                                    ;#5869: 74 01
        ret                                                    ;#586B: C3
        mov     di, 4664h                                      ;#586C: BF 64 46
        call    near 2F9Fh                                     ;#586F: E8 2D D7
        jmp     near 2EADh                                     ;#5872: E9 38 D6
        mov     dx, 837h                                       ;#5875: BA 37 08
        jmp     near 2EE9h                                     ;#5878: E9 6E D6
        mov     si, bp                                         ;#587B: 8B F5
        call    near 58B0h                                     ;#587D: E8 30 00
        stc                                                    ;#5880: F9
        jcxz    58AFh                                          ;#5881: E3 2C
        call    near 301Fh                                     ;#5883: E8 99 D7
        xchg    bp, si                                         ;#5886: 87 F5
        lodsw                                                  ;#5888: AD
        cmp     ax, 3D3Dh                                      ;#5889: 3D 3D 3D
        clc                                                    ;#588C: F8
        jnz     short 58AFh                                    ;#588D: 75 20
        xchg    bp, si                                         ;#588F: 87 F5
        call    near 301Fh                                     ;#5891: E8 8B D7
        stc                                                    ;#5894: F9
        jz      short 58AFh                                    ;#5895: 74 18
        mov     bx, cx                                         ;#5897: 8B D9
        mov     di, bp                                         ;#5899: 8B FD
        call    near 58B0h                                     ;#589B: E8 12 00
        stc                                                    ;#589E: F9
        jcxz    58AFh                                          ;#589F: E3 0E
        cmp     cx, bx                                         ;#58A1: 3B CB
        jnz     short 58A9h                                    ;#58A3: 75 04
        rep     cmpsb                                          ;#58A5: F3 A6
        jz      short 58ADh                                    ;#58A7: 74 04
        not     byte [49C9h]                                   ;#58A9: F6 16 C9 49
        xor     cx, cx                                         ;#58AD: 33 C9
        ret                                                    ;#58AF: C3
        xor     cx, cx                                         ;#58B0: 33 C9
        mov     ax, [bp]                                       ;#58B2: 8B 46 00
        call    near 3000h                                     ;#58B5: E8 48 D7
        jz      short 58C3h                                    ;#58B8: 74 09
        cmp     ax, 3D3Dh                                      ;#58BA: 3D 3D 3D
        jz      short 58C3h                                    ;#58BD: 74 04
        inc     bp                                             ;#58BF: 45
        inc     cx                                             ;#58C0: 41
        jmp     short 58B2h                                    ;#58C1: EB EF
        ret                                                    ;#58C3: C3
        push    di                                             ;#58C4: 57
        mov     di, bp                                         ;#58C5: 8B FD
        xor     cx, cx                                         ;#58C7: 33 C9
        mov     al, [bp]                                       ;#58C9: 8A 46 00
        call    near 3000h                                     ;#58CC: E8 31 D7
        jz      short 58D9h                                    ;#58CF: 74 08
        inc     bp                                             ;#58D1: 45
        inc     cx                                             ;#58D2: 41
        call    near 2F00h                                     ;#58D3: E8 2A D6
        stosb                                                  ;#58D6: AA
        jmp     short 58C9h                                    ;#58D7: EB F0
        pop     di                                             ;#58D9: 5F
        ret                                                    ;#58DA: C3
        mov     si, bp                                         ;#58DB: 8B F5
        mov     di, 4A1Ch                                      ;#58DD: BF 1C 4A
        mov     cx, 80h                                        ;#58E0: B9 80 00
        call    near 316Ah                                     ;#58E3: E8 84 D8
        jb      short 5934h                                    ;#58E6: 72 4C
        add     di, cx                                         ;#58E8: 03 F9
        mov     al, 0Dh                                        ;#58EA: B0 0D
        stosb                                                  ;#58EC: AA
        mov     bp, si                                         ;#58ED: 8B EE
        call    near 301Fh                                     ;#58EF: E8 2D D7
        mov     si, bp                                         ;#58F2: 8B F5
        call    near 58C4h                                     ;#58F4: E8 CD FF
        jcxz    5936h                                          ;#58F7: E3 3D
        call    near 301Fh                                     ;#58F9: E8 23 D7
        jz      short 5936h                                    ;#58FC: 74 38
        mov     dx, 4A1Ch                                      ;#58FE: BA 1C 4A
        call    near 39E9h                                     ;#5901: E8 E5 E0
        mov     dx, 4A1Ch                                      ;#5904: BA 1C 4A
        mov     di, dx                                         ;#5907: 8B FA
        mov     ax, 7Eh                                        ;#5909: B8 7E 00
        stosw                                                  ;#590C: AB
        mov     ah, 0Ah                                        ;#590D: B4 0A
        int     21h                                            ;#590F: CD 21
        mov     dx, 52Eh                                       ;#5911: BA 2E 05
        call    near 39EEh                                     ;#5914: E8 D7 E0
        mov     bx, cx                                         ;#5917: 8B D9
        push    bp                                             ;#5919: 55
        mov     bp, di                                         ;#591A: 8B EF
        call    near 301Fh                                     ;#591C: E8 00 D7
        mov     di, bp                                         ;#591F: 8B FD
        call    near 58C4h                                     ;#5921: E8 A0 FF
        pop     bp                                             ;#5924: 5D
        cmp     cx, bx                                         ;#5925: 3B CB
        jnz     short 592Dh                                    ;#5927: 75 04
        rep     cmpsb                                          ;#5929: F3 A6
        jz      short 5931h                                    ;#592B: 74 04
        not     byte [49C9h]                                   ;#592D: F6 16 C9 49
        xor     cx, cx                                         ;#5931: 33 C9
        ret                                                    ;#5933: C3
        jcxz    5938h                                          ;#5934: E3 02
        stc                                                    ;#5936: F9
        ret                                                    ;#5937: C3
        dec     cx                                             ;#5938: 49
        clc                                                    ;#5939: F8
        ret                                                    ;#593A: C3
        mov     si, bp                                         ;#593B: 8B F5
        mov     di, 0C67h                                      ;#593D: BF 67 0C
        call    near 3140h                                     ;#5940: E8 FD D7
        jcxz    5956h                                          ;#5943: E3 11
        mov     al, [si]                                       ;#5945: 8A 04
        cmp     al, 3Dh                                        ;#5947: 3C 3D
        jz      short 5958h                                    ;#5949: 74 0D
        cmp     al, [4662h]                                    ;#594B: 3A 06 62 46
        jz      short 5958h                                    ;#594F: 74 07
        call    near 3004h                                     ;#5951: E8 B0 D6
        jz      short 5958h                                    ;#5954: 74 02
        stc                                                    ;#5956: F9
        ret                                                    ;#5957: C3
        mov     bp, si                                         ;#5958: 8B EE
        call    near 301Fh                                     ;#595A: E8 C2 D6
        jz      short 5956h                                    ;#595D: 74 F7
        jmp     cx                                             ;#595F: FF E1
        not     byte [49C9h]                                   ;#5961: F6 16 C9 49
        mov     cx, 0FFFFh                                     ;#5965: B9 FF FF
        clc                                                    ;#5968: F8
        ret                                                    ;#5969: C3
        cmp     al, 3Dh                                        ;#596A: 3C 3D
        jnz     short 5971h                                    ;#596C: 75 03
        call    near 301Eh                                     ;#596E: E8 AD D6
        mov     ah, 3                                          ;#5971: B4 03
        call    near 322Bh                                     ;#5973: E8 B5 D8
        jb      short 5997h                                    ;#5976: 72 1F
        or      dh, dh                                         ;#5978: 0A F6
        jnz     short 5997h                                    ;#597A: 75 1B
        mov     al, [bp]                                       ;#597C: 8A 46 00
        call    near 3004h                                     ;#597F: E8 82 D6
        jnz     short 5997h                                    ;#5982: 75 13
        push    ds                                             ;#5984: 1E
        mov     ds, [4660h]                                    ;#5985: 8E 1E 60 46
        cmp     [28Bh], dl                                     ;#5989: 38 16 8B 02
        pop     ds                                             ;#598D: 1F
        jnb     short 5994h                                    ;#598E: 73 04
        not     byte [49C9h]                                   ;#5990: F6 16 C9 49
        xor     cx, cx                                         ;#5994: 33 C9
        ret                                                    ;#5996: C3
        stc                                                    ;#5997: F9
        ret                                                    ;#5998: C3
        mov     ax, 281h                                       ;#5999: B8 81 02
        call    near 31F2h                                     ;#599C: E8 53 D8
        jb      short 59F5h                                    ;#599F: 72 54
        mov     [49CAh], ax                                    ;#59A1: A3 CA 49
        mov     di, 49CCh                                      ;#59A4: BF CC 49
        call    near 330Ah                                     ;#59A7: E8 60 D9
        jb      short 59F5h                                    ;#59AA: 72 49
        test    byte [472Dh], 80h                              ;#59AC: F6 06 2D 47 80
        jnz     short 59EFh                                    ;#59B1: 75 3C
        test    word [49CAh], 200h                             ;#59B3: F7 06 CA 49 00 02
        jnz     short 59F3h                                    ;#59B9: 75 38
        call    near 305Ch                                     ;#59BB: E8 9E D6
        mov     dx, 49CCh                                      ;#59BE: BA CC 49
        mov     ah, 4Eh                                        ;#59C1: B4 4E
        xor     cx, cx                                         ;#59C3: 33 C9
        test    word [49CAh], 80h                              ;#59C5: F7 06 CA 49 80 00
        jz      short 59D0h                                    ;#59CB: 74 03
        mov     cx, 10h                                        ;#59CD: B9 10 00
        int     21h                                            ;#59D0: CD 21
        jb      short 59EFh                                    ;#59D2: 72 1B
        cmp     word [47E7h], 0FFFFh                           ;#59D4: 83 3E E7 47 FF
        jz      short 59EFh                                    ;#59D9: 74 14
        test    word [49CAh], 80h                              ;#59DB: F7 06 CA 49 80 00
        jz      short 59F3h                                    ;#59E1: 74 10
        mov     si, 47DAh                                      ;#59E3: BE DA 47
        call    near 3034h                                     ;#59E6: E8 4B D6
        mov     ah, 4Fh                                        ;#59E9: B4 4F
        jnb     short 59D0h                                    ;#59EB: 73 E3
        jmp     short 59F3h                                    ;#59ED: EB 04
        not     byte [49C9h]                                   ;#59EF: F6 16 C9 49
        xor     cx, cx                                         ;#59F3: 33 C9
        ret                                                    ;#59F5: C3
        mov     ds, [4660h]                                    ;#59F6: 8E 1E 60 46
        test    byte [339h], 4                                 ;#59FA: F6 06 39 03 04
        jz      short 5A26h                                    ;#59FF: 74 25
        call    near 301Fh                                     ;#5A01: E8 1B D6
        jnz     short 5A27h                                    ;#5A04: 75 21
        push    ds                                             ;#5A06: 1E
        pop     es                                             ;#5A07: 07
        mov     di, 433h                                       ;#5A08: BF 33 04
        mov     si, 435h                                       ;#5A0B: BE 35 04
        mov     cx, 9                                          ;#5A0E: B9 09 00
        rep     movsw                                          ;#5A11: F3 A5
        cmp     word [di], 0                                   ;#5A13: 83 3D 00
        jz      short 5A26h                                    ;#5A16: 74 0E
        mov     si, [di]                                       ;#5A18: 8B 35
        call    near 3135h                                     ;#5A1A: E8 18 D7
        cmp     byte [si], 0                                   ;#5A1D: 80 3C 00
        jnz     short 5A24h                                    ;#5A20: 75 02
        xor     si, si                                         ;#5A22: 33 F6
        mov     [di], si                                       ;#5A24: 89 35
        ret                                                    ;#5A26: C3
        mov     dx, 15Ch                                       ;#5A27: BA 5C 01
        jmp     near 2EE9h                                     ;#5A2A: E9 BC D4
        mov     ds, [4660h]                                    ;#5A2D: 8E 1E 60 46
        test    byte [339h], 4                                 ;#5A31: F6 06 39 03 04
        jnz     short 5A39h                                    ;#5A36: 75 01
        ret                                                    ;#5A38: C3
        call    near 301Fh                                     ;#5A39: E8 E3 D5
        jz      short 5A78h                                    ;#5A3C: 74 3A
        cmp     al, 3Ah                                        ;#5A3E: 3C 3A
        jnz     short 5A4Bh                                    ;#5A40: 75 09
        inc     bp                                             ;#5A42: 45
        mov     al, [bp]                                       ;#5A43: 8A 46 00
        call    near 3000h                                     ;#5A46: E8 B7 D5
        jz      short 5A78h                                    ;#5A49: 74 2D
        mov     [es:49C5h], bp                                 ;#5A4B: 26 89 2E C5 49
        xor     cx, cx                                         ;#5A50: 33 C9
        inc     cx                                             ;#5A52: 41
        cmp     cx, 8                                          ;#5A53: 83 F9 08
        jnb     short 5A61h                                    ;#5A56: 73 09
        inc     bp                                             ;#5A58: 45
        mov     al, [bp]                                       ;#5A59: 8A 46 00
        call    near 3000h                                     ;#5A5C: E8 A1 D5
        jnz     short 5A52h                                    ;#5A5F: 75 F1
        mov     [es:49C7h], cx                                 ;#5A61: 26 89 0E C7 49
        xor     ax, ax                                         ;#5A66: 33 C0
        mov     [3DFh], ax                                     ;#5A68: A3 DF 03
        mov     [3E1h], ax                                     ;#5A6B: A3 E1 03
        call    near 40E1h                                     ;#5A6E: E8 70 E6
        jnz     short 5A88h                                    ;#5A71: 75 15
        mov     dx, 887h                                       ;#5A73: BA 87 08
        jmp     short 5A7Bh                                    ;#5A76: EB 03
        mov     dx, 85Eh                                       ;#5A78: BA 5E 08
        and     byte [339h], 0FBh                              ;#5A7B: 80 26 39 03 FB
        or      byte [336h], 4                                 ;#5A80: 80 0E 36 03 04
        jmp     near 2EE9h                                     ;#5A85: E9 61 D4
        call    near 4172h                                     ;#5A88: E8 E7 E6
        cmp     al, 3Ah                                        ;#5A8B: 3C 3A
        jnz     short 5A6Eh                                    ;#5A8D: 75 DF
        mov     si, [es:49C5h]                                 ;#5A8F: 26 8B 36 C5 49
        dec     si                                             ;#5A94: 4E
        mov     cx, [es:49C7h]                                 ;#5A95: 26 8B 0E C7 49
        inc     di                                             ;#5A9A: 47
        inc     si                                             ;#5A9B: 46
        mov     al, [es:di]                                    ;#5A9C: 26 8A 05
        call    near 2F00h                                     ;#5A9F: E8 5E D4
        mov     ah, al                                         ;#5AA2: 8A E0
        mov     al, [es:si]                                    ;#5AA4: 26 8A 04
        call    near 2F00h                                     ;#5AA7: E8 56 D4
        cmp     ah, al                                         ;#5AAA: 3A E0
        loope   5A9Ah                                          ;#5AAC: E1 EC
        jnz     short 5A6Eh                                    ;#5AAE: 75 BE
        cmp     word [es:49C7h], 8                             ;#5AB0: 26 83 3E C7 49 08
        jnb     short 5AC1h                                    ;#5AB6: 73 09
        mov     al, [es:di+1]                                  ;#5AB8: 26 8A 45 01
        call    near 3000h                                     ;#5ABC: E8 41 D5
        jnz     short 5A6Eh                                    ;#5ABF: 75 AD
        ret                                                    ;#5AC1: C3
        mov     byte [4DEEh], 0                                ;#5AC2: C6 06 EE 4D 00
        call    near 5CD0h                                     ;#5AC7: E8 06 02
        and     byte [4DC5h], 0F9h                             ;#5ACA: 80 26 C5 4D F9
        mov     di, 4B89h                                      ;#5ACF: BF 89 4B
        mov     bp, 81h                                        ;#5AD2: BD 81 00
        call    near 5E7Ah                                     ;#5AD5: E8 A2 03
        jnb     short 5ADDh                                    ;#5AD8: 73 03
        jmp     near 5CCFh                                     ;#5ADA: E9 F2 01
        mov     di, [4DCFh]                                    ;#5ADD: 8B 3E CF 4D
        call    near 4C01h                                     ;#5AE1: E8 1D F1
        mov     al, [4663h]                                    ;#5AE4: A0 63 46
        cmp     [di-1], al                                     ;#5AE7: 38 45 FF
        jnz     short 5AFDh                                    ;#5AEA: 75 11
        dec     di                                             ;#5AEC: 4F
        call    near 4BF0h                                     ;#5AED: E8 00 F1
        or      byte [4DC8h], 1                                ;#5AF0: 80 0E C8 4D 01
        or      byte [4DC4h], 40h                              ;#5AF5: 80 0E C4 4D 40
        call    near 6025h                                     ;#5AFA: E8 28 05
        call    near 6036h                                     ;#5AFD: E8 36 05
        jnb     short 5B14h                                    ;#5B00: 73 12
        test    byte [4DC4h], 80h                              ;#5B02: F6 06 C4 4D 80
        jz      short 5ADAh                                    ;#5B07: 74 D1
        call    near 5E63h                                     ;#5B09: E8 57 03
        jnz     short 5ADDh                                    ;#5B0C: 75 CF
        call    near 5D3Ch                                     ;#5B0E: E8 2B 02
        jmp     near 5CCFh                                     ;#5B11: E9 BB 01
        mov     cx, [4DE0h]                                    ;#5B14: 8B 0E E0 4D
        jcxz    5B24h                                          ;#5B18: E3 0A
        call    near 5F94h                                     ;#5B1A: E8 77 04
        jnb     short 5B22h                                    ;#5B1D: 73 03
        jmp     near 5CBEh                                     ;#5B1F: E9 9C 01
        loop    5B1Ah                                          ;#5B22: E2 F6
        mov     di, 4C09h                                      ;#5B24: BF 09 4C
        call    near 60A9h                                     ;#5B27: E8 7F 05
        mov     [4DD1h], di                                    ;#5B2A: 89 3E D1 4D
        jz      short 5B6Bh                                    ;#5B2E: 74 3B
        mov     al, [bp]                                       ;#5B30: 8A 46 00
        call    near 2F6Eh                                     ;#5B33: E8 38 D4
        jz      short 5B5Bh                                    ;#5B36: 74 23
        call    near 662Ah                                     ;#5B38: E8 EF 0A
        jz      short 5B63h                                    ;#5B3B: 74 26
        call    near 5D8Ah                                     ;#5B3D: E8 4A 02
        jb      short 5B58h                                    ;#5B40: 72 16
        jz      short 5B6Bh                                    ;#5B42: 74 27
        cmp     ah, 0FFh                                       ;#5B44: 80 FC FF
        jz      short 5B55h                                    ;#5B47: 74 0C
        mov     al, [bp]                                       ;#5B49: 8A 46 00
        call    near 2F00h                                     ;#5B4C: E8 B1 D3
        mov     [di], al                                       ;#5B4F: 88 05
        inc     di                                             ;#5B51: 47
        inc     bp                                             ;#5B52: 45
        jmp     short 5B30h                                    ;#5B53: EB DB
        call    near 5D41h                                     ;#5B55: E8 E9 01
        jmp     near 5CCFh                                     ;#5B58: E9 74 01
        inc     di                                             ;#5B5B: 47
        mov     [4DD1h], di                                    ;#5B5C: 89 3E D1 4D
        dec     di                                             ;#5B60: 4F
        jmp     short 5B4Ch                                    ;#5B61: EB E9
        inc     bp                                             ;#5B63: 45
        call    near 5D8Ah                                     ;#5B64: E8 23 02
        jb      short 5B58h                                    ;#5B67: 72 EF
        jnz     short 5B55h                                    ;#5B69: 75 EA
        cmp     byte [di-1], 3Ah                               ;#5B6B: 80 7D FF 3A
        jnz     short 5B8Ch                                    ;#5B6F: 75 1B
        mov     si, 4C09h                                      ;#5B71: BE 09 4C
        call    near 666Bh                                     ;#5B74: E8 F4 0A
        cmp     byte [di], 0                                   ;#5B77: 80 3D 00
        jz      short 5B7Fh                                    ;#5B7A: 74 03
        inc     di                                             ;#5B7C: 47
        jmp     short 5B77h                                    ;#5B7D: EB F8
        mov     al, [4663h]                                    ;#5B7F: A0 63 46
        cmp     [di-1], al                                     ;#5B82: 38 45 FF
        jz      short 5B94h                                    ;#5B85: 74 0D
        mov     [di], al                                       ;#5B87: 88 05
        inc     di                                             ;#5B89: 47
        jmp     short 5B94h                                    ;#5B8A: EB 08
        mov     al, [4663h]                                    ;#5B8C: A0 63 46
        cmp     [di-1], al                                     ;#5B8F: 38 45 FF
        jnz     short 5BAEh                                    ;#5B92: 75 1A
        mov     word [di], 2E2Ah                               ;#5B94: C7 05 2A 2E
        mov     word [di+2], 2Ah                               ;#5B98: C7 45 02 2A 00
        mov     [4DD1h], di                                    ;#5B9D: 89 3E D1 4D
        or      byte [4DC8h], 2                                ;#5BA1: 80 0E C8 4D 02
        or      byte [4DC5h], 2                                ;#5BA6: 80 0E C5 4D 02
        inc     di                                             ;#5BAB: 47
        inc     di                                             ;#5BAC: 47
        inc     di                                             ;#5BAD: 47
        mov     byte [di], 0                                   ;#5BAE: C6 05 00
        mov     si, [4DD1h]                                    ;#5BB1: 8B 36 D1 4D
        call    near 5D13h                                     ;#5BB5: E8 5B 01
        jnb     short 5BD6h                                    ;#5BB8: 73 1C
        or      byte [4DC8h], 2                                ;#5BBA: 80 0E C8 4D 02
        cmp     byte [4DC8h], 3                                ;#5BBF: 80 3E C8 4D 03
        jnz     short 5BCBh                                    ;#5BC4: 75 05
        mov     byte [4DC7h], 1                                ;#5BC6: C6 06 C7 4D 01
        mov     si, [4DD1h]                                    ;#5BCB: 8B 36 D1 4D
        mov     di, [4DCFh]                                    ;#5BCF: 8B 3E CF 4D
        call    near 5D47h                                     ;#5BD3: E8 71 01
        cmp     byte [49BDh], 0                                ;#5BD6: 80 3E BD 49 00
        jnz     short 5BE8h                                    ;#5BDB: 75 0B
        call    near 6641h                                     ;#5BDD: E8 61 0A
        inc     byte [49BDh]                                   ;#5BE0: FE 06 BD 49
        or      al, al                                         ;#5BE4: 0A C0
        jnz     short 5BF6h                                    ;#5BE6: 75 0E
        mov     ax, 3D00h                                      ;#5BE8: B8 00 3D
        mov     dx, 4C09h                                      ;#5BEB: BA 09 4C
        int     21h                                            ;#5BEE: CD 21
        jnb     short 5C08h                                    ;#5BF0: 73 16
        cmp     al, 2                                          ;#5BF2: 3C 02
        jz      short 5C43h                                    ;#5BF4: 74 4D
        test    byte [4DC5h], 2                                ;#5BF6: F6 06 C5 4D 02
        jnz     short 5C43h                                    ;#5BFB: 75 46
        mov     di, 4C09h                                      ;#5BFD: BF 09 4C
        call    near 4C01h                                     ;#5C00: E8 FE EF
        call    near 4BF0h                                     ;#5C03: E8 EA EF
        jmp     short 5B9Dh                                    ;#5C06: EB 95
        mov     bx, ax                                         ;#5C08: 8B D8
        push    bx                                             ;#5C0A: 53
        mov     ax, 4400h                                      ;#5C0B: B8 00 44
        int     21h                                            ;#5C0E: CD 21
        test    dl, 80h                                        ;#5C10: F6 C2 80
        jnz     short 5C1Ch                                    ;#5C13: 75 07
        or      byte [4DC5h], 4                                ;#5C15: 80 0E C5 4D 04
        jmp     short 5C3Eh                                    ;#5C1A: EB 22
        or      byte [4DC5h], 1                                ;#5C1C: 80 0E C5 4D 01
        or      byte [4DC4h], 20h                              ;#5C21: 80 0E C4 4D 20
        test    byte [4DC3h], 2                                ;#5C26: F6 06 C3 4D 02
        jz      short 5C32h                                    ;#5C2B: 74 05
        or      byte [4DC4h], 10h                              ;#5C2D: 80 0E C4 4D 10
        test    byte [4DECh], 3                                ;#5C32: F6 06 EC 4D 03
        jnz     short 5C3Eh                                    ;#5C37: 75 05
        or      byte [4DC4h], 1                                ;#5C39: 80 0E C4 4D 01
        pop     bx                                             ;#5C3E: 5B
        mov     ah, 3Eh                                        ;#5C3F: B4 3E
        int     21h                                            ;#5C41: CD 21
        call    near 5E42h                                     ;#5C43: E8 FC 01
        jb      short 5C74h                                    ;#5C46: 72 2C
        call    near 5E08h                                     ;#5C48: E8 BD 01
        jb      short 5C74h                                    ;#5C4B: 72 27
        call    near 607Ch                                     ;#5C4D: E8 2C 04
        mov     [4DDCh], dx                                    ;#5C50: 89 16 DC 4D
        mov     word [4DDEh], 0                                ;#5C54: C7 06 DE 4D 00 00
        test    byte [4DC4h], 88h                              ;#5C5A: F6 06 C4 4D 88
        jnz     short 5C66h                                    ;#5C5F: 75 05
        call    near 62DBh                                     ;#5C61: E8 77 06
        jz      short 5C90h                                    ;#5C64: 74 2A
        mov     byte [4DEFh], 0                                ;#5C66: C6 06 EF 4D 00
        call    near 6335h                                     ;#5C6B: E8 C7 06
        jb      short 5CACh                                    ;#5C6E: 72 3C
        inc     word [4DE6h]                                   ;#5C70: FF 06 E6 4D
        cmp     byte [4DC7h], 0                                ;#5C74: 80 3E C7 4D 00
        jz      short 5CBEh                                    ;#5C79: 74 43
        inc     word [4DE0h]                                   ;#5C7B: FF 06 E0 4D
        xor     ax, ax                                         ;#5C7F: 33 C0
        mov     [4DC4h], al                                    ;#5C81: A2 C4 4D
        mov     [4DCDh], ax                                    ;#5C84: A3 CD 4D
        mov     [4DC6h], al                                    ;#5C87: A2 C6 4D
        mov     [49BDh], al                                    ;#5C8A: A2 BD 49
        jmp     near 5ACAh                                     ;#5C8D: E9 3A FE
        test    word [4DF0h], 8                                ;#5C90: F7 06 F0 4D 08 00
        jz      short 5C9Fh                                    ;#5C96: 74 07
        call    near 6188h                                     ;#5C98: E8 ED 04
        jb      short 5CBEh                                    ;#5C9B: 72 21
        jmp     short 5C70h                                    ;#5C9D: EB D1
        cmp     word [4D96h], 0FFFFh                           ;#5C9F: 83 3E 96 4D FF
        jz      short 5C66h                                    ;#5CA4: 74 C0
        mov     dx, 0B74h                                      ;#5CA6: BA 74 0B
        call    near 4C07h                                     ;#5CA9: E8 5B EF
        call    near 6176h                                     ;#5CAC: E8 C7 04
        call    near 6167h                                     ;#5CAF: E8 B5 04
        and     byte [4DEDh], 0FCh                             ;#5CB2: 80 26 ED 4D FC
        cmp     byte [4DEFh], 1                                ;#5CB7: 80 3E EF 4D 01
        jnz     short 5C74h                                    ;#5CBC: 75 B6
        mov     si, [4DE6h]                                    ;#5CBE: 8B 36 E6 4D
        xor     di, di                                         ;#5CC2: 33 FF
        mov     ah, 5                                          ;#5CC4: B4 05
        call    near 327Bh                                     ;#5CC6: E8 B2 D5
        mov     dx, 0BDEh                                      ;#5CC9: BA DE 0B
        call    near 39EEh                                     ;#5CCC: E8 1F DD
        ret                                                    ;#5CCF: C3
        xor     ax, ax                                         ;#5CD0: 33 C0
        mov     [4DC4h], al                                    ;#5CD2: A2 C4 4D
        mov     [4DC5h], al                                    ;#5CD5: A2 C5 4D
        mov     [4DC3h], al                                    ;#5CD8: A2 C3 4D
        mov     [4DC6h], al                                    ;#5CDB: A2 C6 4D
        mov     [4DC7h], al                                    ;#5CDE: A2 C7 4D
        mov     [4DC8h], al                                    ;#5CE1: A2 C8 4D
        mov     [4DECh], al                                    ;#5CE4: A2 EC 4D
        mov     [4DF0h], ax                                    ;#5CE7: A3 F0 4D
        mov     [4DE0h], ax                                    ;#5CEA: A3 E0 4D
        mov     [4DCDh], ax                                    ;#5CED: A3 CD 4D
        mov     [4DEDh], al                                    ;#5CF0: A2 ED 4D
        mov     [4DE2h], ax                                    ;#5CF3: A3 E2 4D
        mov     [4DE4h], ax                                    ;#5CF6: A3 E4 4D
        mov     [4DE6h], ax                                    ;#5CF9: A3 E6 4D
        mov     [49BDh], al                                    ;#5CFC: A2 BD 49
        ret                                                    ;#5CFF: C3
        mov     al, [bp]                                       ;#5D00: 8A 46 00
        cmp     al, 0Dh                                        ;#5D03: 3C 0D
        jz      short 5D0Fh                                    ;#5D05: 74 08
        call    near 662Ah                                     ;#5D07: E8 20 09
        jz      short 5D11h                                    ;#5D0A: 74 05
        inc     bp                                             ;#5D0C: 45
        jmp     short 5D00h                                    ;#5D0D: EB F1
        stc                                                    ;#5D0F: F9
        ret                                                    ;#5D10: C3
        clc                                                    ;#5D11: F8
        ret                                                    ;#5D12: C3
        mov     bx, si                                         ;#5D13: 8B DE
        mov     al, [si]                                       ;#5D15: 8A 04
        cmp     al, 2Eh                                        ;#5D17: 3C 2E
        jz      short 5D32h                                    ;#5D19: 74 17
        cmp     al, 0                                          ;#5D1B: 3C 00
        clc                                                    ;#5D1D: F8
        jz      short 5D29h                                    ;#5D1E: 74 09
        call    near 2FE0h                                     ;#5D20: E8 BD D2
        jz      short 5D28h                                    ;#5D23: 74 03
        inc     si                                             ;#5D25: 46
        jmp     short 5D15h                                    ;#5D26: EB ED
        stc                                                    ;#5D28: F9
        pushf                                                  ;#5D29: 9C
        push    si                                             ;#5D2A: 56
        sub     si, bx                                         ;#5D2B: 2B F3
        mov     cx, si                                         ;#5D2D: 8B CE
        pop     si                                             ;#5D2F: 5E
        popf                                                   ;#5D30: 9D
        ret                                                    ;#5D31: C3
        mov     byte [4DD3h], 1                                ;#5D32: C6 06 D3 4D 01
        mov     bx, si                                         ;#5D37: 8B DE
        inc     si                                             ;#5D39: 46
        jmp     short 5D15h                                    ;#5D3A: EB D9
        mov     dx, 9E9h                                       ;#5D3C: BA E9 09
        jmp     short 5D44h                                    ;#5D3F: EB 03
        mov     dx, 184h                                       ;#5D41: BA 84 01
        jmp     near 4C07h                                     ;#5D44: E9 C0 EE
        push    si                                             ;#5D47: 56
        push    di                                             ;#5D48: 57
        mov     byte [4DD3h], 0                                ;#5D49: C6 06 D3 4D 00
        call    near 5D13h                                     ;#5D4E: E8 C2 FF
        jnb     short 5D6Ah                                    ;#5D51: 73 17
        call    near 5FA5h                                     ;#5D53: E8 4F 02
        cmp     byte [si], 3Fh                                 ;#5D56: 80 3C 3F
        jnz     short 5D5Fh                                    ;#5D59: 75 04
        mov     [si], al                                       ;#5D5B: 88 04
        jmp     short 5D66h                                    ;#5D5D: EB 07
        push    bp                                             ;#5D5F: 55
        mov     bp, si                                         ;#5D60: 8B EE
        call    near 5FC7h                                     ;#5D62: E8 62 02
        pop     bp                                             ;#5D65: 5D
        pop     di                                             ;#5D66: 5F
        pop     si                                             ;#5D67: 5E
        jmp     short 5D47h                                    ;#5D68: EB DD
        pop     si                                             ;#5D6A: 5E
        pop     di                                             ;#5D6B: 5F
        ret                                                    ;#5D6C: C3
        call    near 5DABh                                     ;#5D6D: E8 3B 00
        pushf                                                  ;#5D70: 9C
        cmp     ah, 0FFh                                       ;#5D71: 80 FC FF
        jnz     short 5D88h                                    ;#5D74: 75 12
        and     byte [4DC4h], 0FCh                             ;#5D76: 80 26 C4 4D FC
        or      [4DC4h], bl                                    ;#5D7B: 08 1E C4 4D
        and     byte [4DC3h], 0FCh                             ;#5D7F: 80 26 C3 4D FC
        or      [4DC3h], bl                                    ;#5D84: 08 1E C3 4D
        popf                                                   ;#5D88: 9D
        ret                                                    ;#5D89: C3
        call    near 5DABh                                     ;#5D8A: E8 1E 00
        pushf                                                  ;#5D8D: 9C
        cmp     ah, 0FFh                                       ;#5D8E: 80 FC FF
        jnz     short 5DA9h                                    ;#5D91: 75 16
        mov     cl, 4                                          ;#5D93: B1 04
        shl     bl, cl                                         ;#5D95: D2 E3
        and     byte [4DC4h], 0CFh                             ;#5D97: 80 26 C4 4D CF
        or      [4DC4h], bl                                    ;#5D9C: 08 1E C4 4D
        and     byte [4DC3h], 0CFh                             ;#5DA0: 80 26 C3 4D CF
        or      [4DC3h], bl                                    ;#5DA5: 08 1E C3 4D
        popf                                                   ;#5DA9: 9D
        ret                                                    ;#5DAA: C3
        mov     ax, 3DBh                                       ;#5DAB: B8 DB 03
        call    near 31F2h                                     ;#5DAE: E8 41 D4
        mov     [4DF0h], ax                                    ;#5DB1: A3 F0 4D
        pushf                                                  ;#5DB4: 9C
        mov     bl, 0                                          ;#5DB5: B3 00
        test    ax, 1                                          ;#5DB7: A9 01 00
        jz      short 5DBFh                                    ;#5DBA: 74 03
        or      bl, 1                                          ;#5DBC: 80 CB 01
        test    ax, 2                                          ;#5DBF: A9 02 00
        jz      short 5DC7h                                    ;#5DC2: 74 03
        or      bl, 2                                          ;#5DC4: 80 CB 02
        popf                                                   ;#5DC7: 9D
        jb      short 5E03h                                    ;#5DC8: 72 39
        test    ax, 200h                                       ;#5DCA: A9 00 02
        jz      short 5DE7h                                    ;#5DCD: 74 18
        mov     ah, 54h                                        ;#5DCF: B4 54
        int     21h                                            ;#5DD1: CD 21
        or      al, al                                         ;#5DD3: 0A C0
        jnz     short 5DE7h                                    ;#5DD5: 75 10
        push    ds                                             ;#5DD7: 1E
        mov     ds, [4660h]                                    ;#5DD8: 8E 1E 60 46
        mov     byte [27Ah], 0                                 ;#5DDC: C6 06 7A 02 00
        pop     ds                                             ;#5DE1: 1F
        mov     ax, 2E01h                                      ;#5DE2: B8 01 2E
        int     21h                                            ;#5DE5: CD 21
        test    word [4DF0h], 10h                              ;#5DE7: F7 06 F0 4D 10 00
        jz      short 5DF4h                                    ;#5DED: 74 05
        or      byte [4DC4h], 40h                              ;#5DEF: 80 0E C4 4D 40
        test    bl, 3                                          ;#5DF4: F6 C3 03
        mov     ah, 0                                          ;#5DF7: B4 00
        jz      short 5DFDh                                    ;#5DF9: 74 02
        mov     ah, 0FFh                                       ;#5DFB: B4 FF
        cmp     byte [bp], 0Dh                                 ;#5DFD: 80 7E 00 0D
        clc                                                    ;#5E01: F8
        ret                                                    ;#5E02: C3
        call    near 5D41h                                     ;#5E03: E8 3B FF
        stc                                                    ;#5E06: F9
        ret                                                    ;#5E07: C3
        test    word [4DF0h], 80h                              ;#5E08: F7 06 F0 4D 80 00
        jnz     short 5E40h                                    ;#5E0E: 75 30
        test    byte [4DC5h], 4                                ;#5E10: F6 06 C5 4D 04
        jz      short 5E40h                                    ;#5E15: 74 29
        xor     dl, dl                                         ;#5E17: 32 D2
        mov     ax, 1817h                                      ;#5E19: B8 17 18
        int     21h                                            ;#5E1C: CD 21
        or      al, al                                         ;#5E1E: 0A C0
        jz      short 5E40h                                    ;#5E20: 74 1E
        mov     dx, 0BA8h                                      ;#5E22: BA A8 0B
        call    near 39EEh                                     ;#5E25: E8 C6 DB
        mov     dx, 4C09h                                      ;#5E28: BA 09 4C
        call    near 39E4h                                     ;#5E2B: E8 B6 DB
        mov     dx, 0BC7h                                      ;#5E2E: BA C7 0B
        call    near 39EEh                                     ;#5E31: E8 BA DB
        call    near 4B10h                                     ;#5E34: E8 D9 EC
        jnb     short 5E40h                                    ;#5E37: 73 07
        mov     byte [4DC6h], 0                                ;#5E39: C6 06 C6 4D 00
        stc                                                    ;#5E3E: F9
        ret                                                    ;#5E3F: C3
        clc                                                    ;#5E40: F8
        ret                                                    ;#5E41: C3
        test    word [4DF0h], 40h                              ;#5E42: F7 06 F0 4D 40 00
        clc                                                    ;#5E48: F8
        jz      short 5E62h                                    ;#5E49: 74 17
        push    dx                                             ;#5E4B: 52
        mov     dx, 0B98h                                      ;#5E4C: BA 98 0B
        call    near 39EEh                                     ;#5E4F: E8 9C DB
        mov     dx, 4C09h                                      ;#5E52: BA 09 4C
        call    near 39E4h                                     ;#5E55: E8 8C DB
        mov     dx, 0BD2h                                      ;#5E58: BA D2 0B
        call    near 39EEh                                     ;#5E5B: E8 90 DB
        call    near 4B10h                                     ;#5E5E: E8 AF EC
        pop     dx                                             ;#5E61: 5A
        ret                                                    ;#5E62: C3
        mov     bp, [4DCDh]                                    ;#5E63: 8B 2E CD 4D
        or      bp, bp                                         ;#5E67: 0B ED
        jnz     short 5E6Dh                                    ;#5E69: 75 02
        clc                                                    ;#5E6B: F8
        ret                                                    ;#5E6C: C3
        and     byte [4DC4h], 0FBh                             ;#5E6D: 80 26 C4 4D FB
        and     byte [4DC8h], 0FEh                             ;#5E72: 80 26 C8 4D FE
        mov     di, 4B89h                                      ;#5E77: BF 89 4B
        mov     word [4DCDh], 0                                ;#5E7A: C7 06 CD 4D 00 00
        call    near 5D6Dh                                     ;#5E80: E8 EA FE
        jnb     short 5E88h                                    ;#5E83: 73 03
        jmp     near 5F0Ah                                     ;#5E85: E9 82 00
        jz      short 5F06h                                    ;#5E88: 74 7C
        test    byte [4DECh], 80h                              ;#5E8A: F6 06 EC 4D 80
        jnz     short 5E99h                                    ;#5E8F: 75 08
        mov     al, [4DC4h]                                    ;#5E91: A0 C4 4D
        or      al, 80h                                        ;#5E94: 0C 80
        mov     [4DECh], al                                    ;#5E96: A2 EC 4D
        call    near 60A9h                                     ;#5E99: E8 0D 02
        jz      short 5F06h                                    ;#5E9C: 74 68
        mov     [4DCFh], di                                    ;#5E9E: 89 3E CF 4D
        mov     al, [bp]                                       ;#5EA2: 8A 46 00
        cmp     al, 2Bh                                        ;#5EA5: 3C 2B
        jz      short 5F13h                                    ;#5EA7: 74 6A
        call    near 2F6Eh                                     ;#5EA9: E8 C2 D0
        jz      short 5F0Bh                                    ;#5EAC: 74 5D
        call    near 662Ah                                     ;#5EAE: E8 79 07
        jz      short 5ECBh                                    ;#5EB1: 74 18
        call    near 5D6Dh                                     ;#5EB3: E8 B7 FE
        jb      short 5F0Ah                                    ;#5EB6: 72 52
        jz      short 5EE9h                                    ;#5EB8: 74 2F
        cmp     ah, 0FFh                                       ;#5EBA: 80 FC FF
        jz      short 5EE3h                                    ;#5EBD: 74 24
        mov     al, [bp]                                       ;#5EBF: 8A 46 00
        call    near 2F00h                                     ;#5EC2: E8 3B D0
        mov     [di], al                                       ;#5EC5: 88 05
        inc     di                                             ;#5EC7: 47
        inc     bp                                             ;#5EC8: 45
        jmp     short 5EA2h                                    ;#5EC9: EB D7
        cmp     al, 3Ah                                        ;#5ECB: 3C 3A
        jz      short 5EDBh                                    ;#5ECD: 74 0C
        call    near 301Fh                                     ;#5ECF: E8 4D D1
        call    near 662Ah                                     ;#5ED2: E8 55 07
        jnz     short 5EDCh                                    ;#5ED5: 75 05
        cmp     al, 3Ah                                        ;#5ED7: 3C 3A
        jz      short 5F06h                                    ;#5ED9: 74 2B
        inc     bp                                             ;#5EDB: 45
        call    near 5D6Dh                                     ;#5EDC: E8 8E FE
        jb      short 5F0Ah                                    ;#5EDF: 72 29
        jz      short 5EE9h                                    ;#5EE1: 74 06
        cmp     byte [bp], 2Bh                                 ;#5EE3: 80 7E 00 2B
        jz      short 5F13h                                    ;#5EE7: 74 2A
        mov     byte [di], 0                                   ;#5EE9: C6 05 00
        mov     si, [4DCFh]                                    ;#5EEC: 8B 36 CF 4D
        call    near 5D13h                                     ;#5EF0: E8 20 FE
        jnb     short 5EFFh                                    ;#5EF3: 73 0A
        or      byte [4DC8h], 1                                ;#5EF5: 80 0E C8 4D 01
        or      byte [4DC4h], 40h                              ;#5EFA: 80 0E C4 4D 40
        call    near 6025h                                     ;#5EFF: E8 23 01
        or      bp, bp                                         ;#5F02: 0B ED
        clc                                                    ;#5F04: F8
        ret                                                    ;#5F05: C3
        call    near 5D41h                                     ;#5F06: E8 38 FE
        stc                                                    ;#5F09: F9
        ret                                                    ;#5F0A: C3
        inc     di                                             ;#5F0B: 47
        mov     [4DCFh], di                                    ;#5F0C: 89 3E CF 4D
        dec     di                                             ;#5F10: 4F
        jmp     short 5EC2h                                    ;#5F11: EB AF
        call    near 301Eh                                     ;#5F13: E8 08 D1
        jz      short 5EE9h                                    ;#5F16: 74 D1
        mov     al, [bp]                                       ;#5F18: 8A 46 00
        call    near 6632h                                     ;#5F1B: E8 14 07
        jnz     short 5F41h                                    ;#5F1E: 75 21
        call    near 301Eh                                     ;#5F20: E8 FB D0
        jz      short 5EE9h                                    ;#5F23: 74 C4
        mov     al, [bp]                                       ;#5F25: 8A 46 00
        call    near 6632h                                     ;#5F28: E8 07 07
        jnz     short 5F06h                                    ;#5F2B: 75 D9
        inc     bp                                             ;#5F2D: 45
        or      byte [4DC4h], 48h                              ;#5F2E: 80 0E C4 4D 48
        call    near 5D6Dh                                     ;#5F33: E8 37 FE
        jb      short 5F0Ah                                    ;#5F36: 72 D2
        jz      short 5EE9h                                    ;#5F38: 74 AF
        cmp     byte [bp], 2Bh                                 ;#5F3A: 80 7E 00 2B
        jnz     short 5EE9h                                    ;#5F3E: 75 A9
        inc     bp                                             ;#5F40: 45
        or      byte [4DC4h], 0C0h                             ;#5F41: 80 0E C4 4D C0
        mov     [4DCDh], bp                                    ;#5F46: 89 2E CD 4D
        call    near 5D6Dh                                     ;#5F4A: E8 20 FE
        jb      short 5F0Ah                                    ;#5F4D: 72 BB
        cmp     ah, 0FFh                                       ;#5F4F: 80 FC FF
        jz      short 5F06h                                    ;#5F52: 74 B2
        call    near 301Fh                                     ;#5F54: E8 C8 D0
        jz      short 5EE9h                                    ;#5F57: 74 90
        cmp     byte [bp+1], 3Ah                               ;#5F59: 80 7E 01 3A
        jnz     short 5F61h                                    ;#5F5D: 75 02
        inc     bp                                             ;#5F5F: 45
        inc     bp                                             ;#5F60: 45
        mov     al, [bp]                                       ;#5F61: 8A 46 00
        cmp     al, 0Dh                                        ;#5F64: 3C 0D
        jz      short 5F80h                                    ;#5F66: 74 18
        inc     bp                                             ;#5F68: 45
        call    near 662Ah                                     ;#5F69: E8 BE 06
        jnz     short 5F61h                                    ;#5F6C: 75 F3
        call    near 301Fh                                     ;#5F6E: E8 AE D0
        jz      short 5F80h                                    ;#5F71: 74 0D
        call    near 5D6Dh                                     ;#5F73: E8 F7 FD
        jb      short 5F0Ah                                    ;#5F76: 72 92
        inc     bp                                             ;#5F78: 45
        cmp     byte [bp-1], 2Bh                               ;#5F79: 80 7E FF 2B
        jz      short 5F4Ah                                    ;#5F7D: 74 CB
        dec     bp                                             ;#5F7F: 4D
        jmp     near 5EE9h                                     ;#5F80: E9 66 FF
        test    byte [4DC8h], 1                                ;#5F83: F6 06 C8 4D 01
        clc                                                    ;#5F88: F8
        jz      short 5FA4h                                    ;#5F89: 74 19
        mov     ah, 4Eh                                        ;#5F8B: B4 4E
        mov     dx, 4B89h                                      ;#5F8D: BA 89 4B
        xor     cx, cx                                         ;#5F90: 33 C9
        jmp     short 5F96h                                    ;#5F92: EB 02
        mov     ah, 4Fh                                        ;#5F94: B4 4F
        int     21h                                            ;#5F96: CD 21
        jb      short 5FA4h                                    ;#5F98: 72 0A
        mov     si, 4DA7h                                      ;#5F9A: BE A7 4D
        mov     di, [4DCFh]                                    ;#5F9D: 8B 3E CF 4D
        call    near 602Ch                                     ;#5FA1: E8 88 00
        ret                                                    ;#5FA4: C3
        inc     cx                                             ;#5FA5: 41
        cmp     byte [4DD3h], 0                                ;#5FA6: 80 3E D3 4D 00
        jz      short 5FB8h                                    ;#5FAB: 74 0B
        inc     di                                             ;#5FAD: 47
        cmp     byte [di], 0                                   ;#5FAE: 80 3D 00
        jz      short 5FC4h                                    ;#5FB1: 74 11
        cmp     byte [di], 2Eh                                 ;#5FB3: 80 3D 2E
        jnz     short 5FADh                                    ;#5FB6: 75 F5
        cmp     byte [di], 0                                   ;#5FB8: 80 3D 00
        jz      short 5FC4h                                    ;#5FBB: 74 07
        inc     di                                             ;#5FBD: 47
        loop    5FB8h                                          ;#5FBE: E2 F8
        dec     di                                             ;#5FC0: 4F
        mov     al, [di]                                       ;#5FC1: 8A 05
        ret                                                    ;#5FC3: C3
        mov     al, 20h                                        ;#5FC4: B0 20
        ret                                                    ;#5FC6: C3
        push    bp                                             ;#5FC7: 55
        mov     si, di                                         ;#5FC8: 8B F7
        cmp     byte [4DD3h], 1                                ;#5FCA: 80 3E D3 4D 01
        jnz     short 5FDEh                                    ;#5FCF: 75 0D
        pop     bp                                             ;#5FD1: 5D
        dec     bp                                             ;#5FD2: 4D
        cmp     byte [si], 0                                   ;#5FD3: 80 3C 00
        jz      short 600Ch                                    ;#5FD6: 74 34
        inc     bp                                             ;#5FD8: 45
        call    near 6011h                                     ;#5FD9: E8 35 00
        jmp     short 600Ch                                    ;#5FDC: EB 2E
        cmp     byte [bp+1], 2Eh                               ;#5FDE: 80 7E 01 2E
        jz      short 5FEDh                                    ;#5FE2: 74 09
        cmp     byte [bp+1], 0                                 ;#5FE4: 80 7E 01 00
        jz      short 5FD1h                                    ;#5FE8: 74 E7
        inc     bp                                             ;#5FEA: 45
        jmp     short 5FDEh                                    ;#5FEB: EB F1
        mov     ax, [bp+1]                                     ;#5FED: 8B 46 01
        mov     [4DC9h], ax                                    ;#5FF0: A3 C9 4D
        mov     ax, [bp+3]                                     ;#5FF3: 8B 46 03
        mov     [4DCBh], ax                                    ;#5FF6: A3 CB 4D
        pop     bp                                             ;#5FF9: 5D
        call    near 6011h                                     ;#5FFA: E8 14 00
        mov     ax, [4DC9h]                                    ;#5FFD: A1 C9 4D
        mov     [bp], ax                                       ;#6000: 89 46 00
        mov     ax, [4DCBh]                                    ;#6003: A1 CB 4D
        mov     [bp+2], ax                                     ;#6006: 89 46 02
        add     bp, 4                                          ;#6009: 83 C5 04
        mov     byte [bp], 0                                   ;#600C: C6 46 00 00
        ret                                                    ;#6010: C3
        mov     al, [si]                                       ;#6011: 8A 04
        cmp     al, 0                                          ;#6013: 3C 00
        clc                                                    ;#6015: F8
        jz      short 6024h                                    ;#6016: 74 0C
        cmp     al, 2Eh                                        ;#6018: 3C 2E
        stc                                                    ;#601A: F9
        jz      short 6024h                                    ;#601B: 74 07
        mov     [bp], al                                       ;#601D: 88 46 00
        inc     si                                             ;#6020: 46
        inc     bp                                             ;#6021: 45
        jmp     short 6011h                                    ;#6022: EB ED
        ret                                                    ;#6024: C3
        mov     si, [4DCFh]                                    ;#6025: 8B 36 CF 4D
        mov     di, 4DB6h                                      ;#6029: BF B6 4D
        push    si                                             ;#602C: 56
        movsb                                                  ;#602D: A4
        cmp     byte [si-1], 0                                 ;#602E: 80 7C FF 00
        jnz     short 602Dh                                    ;#6032: 75 F9
        pop     si                                             ;#6034: 5E
        ret                                                    ;#6035: C3
        push    cx                                             ;#6036: 51
        mov     ah, 1Ah                                        ;#6037: B4 1A
        mov     dx, 4D89h                                      ;#6039: BA 89 4D
        int     21h                                            ;#603C: CD 21
        xor     cx, cx                                         ;#603E: 33 C9
        mov     ah, 4Eh                                        ;#6040: B4 4E
        mov     dx, 4B89h                                      ;#6042: BA 89 4B
        int     21h                                            ;#6045: CD 21
        jnb     short 6069h                                    ;#6047: 73 20
        mov     ah, 4Eh                                        ;#6049: B4 4E
        mov     cx, 10h                                        ;#604B: B9 10 00
        int     21h                                            ;#604E: CD 21
        jb      short 605Ch                                    ;#6050: 72 0A
        call    near 4BD4h                                     ;#6052: E8 7F EB
        or      byte [4DC4h], 40h                              ;#6055: 80 0E C4 4D 40
        jmp     short 6037h                                    ;#605A: EB DB
        test    byte [4DC4h], 80h                              ;#605C: F6 06 C4 4D 80
        jnz     short 6066h                                    ;#6061: 75 03
        call    near 5D3Ch                                     ;#6063: E8 D6 FC
        stc                                                    ;#6066: F9
        pop     cx                                             ;#6067: 59
        ret                                                    ;#6068: C3
        cmp     byte [4D96h], 0FFh                             ;#6069: 80 3E 96 4D FF
        jnz     short 6076h                                    ;#606E: 75 06
        or      word [4DC4h], 4                                ;#6070: 81 0E C4 4D 04 00
        call    near 5F9Ah                                     ;#6076: E8 21 FF
        clc                                                    ;#6079: F8
        pop     cx                                             ;#607A: 59
        ret                                                    ;#607B: C3
        push    ds                                             ;#607C: 1E
        mov     ds, [4660h]                                    ;#607D: 8E 1E 60 46
        mov     dx, [272h]                                     ;#6081: 8B 16 72 02
        mov     bx, [274h]                                     ;#6085: 8B 1E 74 02
        pop     ds                                             ;#6089: 1F
        push    dx                                             ;#608A: 52
        mov     dx, bx                                         ;#608B: 8B D3
        mov     cl, 4                                          ;#608D: B1 04
        shl     bx, cl                                         ;#608F: D3 E3
        mov     cl, 0Ch                                        ;#6091: B1 0C
        shr     dx, cl                                         ;#6093: D3 EA
        mov     [4DD8h], bx                                    ;#6095: 89 1E D8 4D
        mov     [4DDAh], dx                                    ;#6099: 89 16 DA 4D
        pop     dx                                             ;#609D: 5A
        ret                                                    ;#609E: C3
        push    ax                                             ;#609F: 50
        mov     ax, ds                                         ;#60A0: 8C D8
        add     ax, 1000h                                      ;#60A2: 05 00 10
        mov     ds, ax                                         ;#60A5: 8E D8
        pop     ax                                             ;#60A7: 58
        ret                                                    ;#60A8: C3
        mov     ax, [bp]                                       ;#60A9: 8B 46 00
        cmp     al, 0Dh                                        ;#60AC: 3C 0D
        jz      short 60BBh                                    ;#60AE: 74 0B
        cmp     ah, 3Ah                                        ;#60B0: 80 FC 3A
        jnz     short 60BBh                                    ;#60B3: 75 06
        inc     bp                                             ;#60B5: 45
        inc     bp                                             ;#60B6: 45
        and     al, 0DFh                                       ;#60B7: 24 DF
        jmp     short 60C4h                                    ;#60B9: EB 09
        mov     al, [cs:4706h]                                 ;#60BB: 2E A0 06 47
        add     ax, 41h                                        ;#60BF: 05 41 00
        mov     ah, 3Ah                                        ;#60C2: B4 3A
        mov     [di], ax                                       ;#60C4: 89 05
        inc     di                                             ;#60C6: 47
        inc     di                                             ;#60C7: 47
        cmp     byte [bp], 0Dh                                 ;#60C8: 80 7E 00 0D
        ret                                                    ;#60CC: C3
        mov     ax, [4DE2h]                                    ;#60CD: A1 E2 4D
        or      ax, ax                                         ;#60D0: 0B C0
        clc                                                    ;#60D2: F8
        jnz     short 611Ch                                    ;#60D3: 75 47
        mov     dx, 4B89h                                      ;#60D5: BA 89 4B
        mov     ax, 3D00h                                      ;#60D8: B8 00 3D
        int     21h                                            ;#60DB: CD 21
        jb      short 611Ch                                    ;#60DD: 72 3D
        mov     byte [4DC6h], 0                                ;#60DF: C6 06 C6 4D 00
        mov     [4DE2h], ax                                    ;#60E4: A3 E2 4D
        push    ax                                             ;#60E7: 50
        test    byte [4DC4h], 40h                              ;#60E8: F6 06 C4 4D 40
        jz      short 60F2h                                    ;#60ED: 74 03
        call    near 65E9h                                     ;#60EF: E8 F7 04
        pop     bx                                             ;#60F2: 5B
        mov     ax, 4202h                                      ;#60F3: B8 02 42
        xor     cx, cx                                         ;#60F6: 33 C9
        mov     dx, cx                                         ;#60F8: 8B D1
        int     21h                                            ;#60FA: CD 21
        mov     [4DD6h], dx                                    ;#60FC: 89 16 D6 4D
        mov     [4DD4h], ax                                    ;#6100: A3 D4 4D
        xor     dx, dx                                         ;#6103: 33 D2
        mov     ax, 4200h                                      ;#6105: B8 00 42
        int     21h                                            ;#6108: CD 21
        mov     ax, 5700h                                      ;#610A: B8 00 57
        int     21h                                            ;#610D: CD 21
        mov     [4DE8h], cx                                    ;#610F: 89 0E E8 4D
        mov     [4DEAh], dx                                    ;#6113: 89 16 EA 4D
        or      byte [4DEDh], 1                                ;#6117: 80 0E ED 4D 01
        ret                                                    ;#611C: C3
        cmp     word [4DE4h], 0                                ;#611D: 83 3E E4 4D 00
        jnz     short 6137h                                    ;#6122: 75 13
        xor     cx, cx                                         ;#6124: 33 C9
        mov     ah, 3Ch                                        ;#6126: B4 3C
        int     21h                                            ;#6128: CD 21
        jb      short 6139h                                    ;#612A: 72 0D
        call    near 6141h                                     ;#612C: E8 12 00
        mov     [4DE4h], ax                                    ;#612F: A3 E4 4D
        or      byte [4DEDh], 2                                ;#6132: 80 0E ED 4D 02
        clc                                                    ;#6137: F8
        ret                                                    ;#6138: C3
        mov     dx, 0A1Eh                                      ;#6139: BA 1E 0A
        call    near 4C07h                                     ;#613C: E8 C8 EA
        stc                                                    ;#613F: F9
        ret                                                    ;#6140: C3
        push    ax                                             ;#6141: 50
        push    bx                                             ;#6142: 53
        push    cx                                             ;#6143: 51
        push    dx                                             ;#6144: 52
        mov     bx, ax                                         ;#6145: 8B D8
        mov     ax, 4400h                                      ;#6147: B8 00 44
        int     21h                                            ;#614A: CD 21
        test    dl, 80h                                        ;#614C: F6 C2 80
        jz      short 6162h                                    ;#614F: 74 11
        test    byte [4DC4h], 20h                              ;#6151: F6 06 C4 4D 20
        jz      short 6162h                                    ;#6156: 74 0A
        xor     dh, dh                                         ;#6158: 32 F6
        or      dl, 20h                                        ;#615A: 80 CA 20
        mov     ax, 4401h                                      ;#615D: B8 01 44
        int     21h                                            ;#6160: CD 21
        pop     dx                                             ;#6162: 5A
        pop     cx                                             ;#6163: 59
        pop     bx                                             ;#6164: 5B
        pop     ax                                             ;#6165: 58
        ret                                                    ;#6166: C3
        test    byte [4DEDh], 2                                ;#6167: F6 06 ED 4D 02
        jz      short 6187h                                    ;#616C: 74 19
        xor     bx, bx                                         ;#616E: 33 DB
        xchg    [4DE4h], bx                                    ;#6170: 87 1E E4 4D
        jmp     short 6183h                                    ;#6174: EB 0D
        test    byte [4DEDh], 1                                ;#6176: F6 06 ED 4D 01
        jz      short 6187h                                    ;#617B: 74 0A
        xor     bx, bx                                         ;#617D: 33 DB
        xchg    [4DE2h], bx                                    ;#617F: 87 1E E2 4D
        mov     ah, 3Eh                                        ;#6183: B4 3E
        int     21h                                            ;#6185: CD 21
        ret                                                    ;#6187: C3
        mov     dx, 4B89h                                      ;#6188: BA 89 4B
        mov     ax, 3D00h                                      ;#618B: B8 00 3D
        int     21h                                            ;#618E: CD 21
        jb      short 6209h                                    ;#6190: 72 77
        mov     [4DE2h], ax                                    ;#6192: A3 E2 4D
        or      byte [4DEDh], 1                                ;#6195: 80 0E ED 4D 01
        push    ax                                             ;#619A: 50
        test    byte [4DC4h], 40h                              ;#619B: F6 06 C4 4D 40
        jz      short 61A5h                                    ;#61A0: 74 03
        call    near 65E9h                                     ;#61A2: E8 44 04
        pop     bx                                             ;#61A5: 5B
        call    near 6606h                                     ;#61A6: E8 5D 04
        jb      short 620Fh                                    ;#61A9: 72 64
        test    byte [4DC4h], 4                                ;#61AB: F6 06 C4 4D 04
        mov     dx, 0ACCh                                      ;#61B0: BA CC 0A
        jnz     short 620Ch                                    ;#61B3: 75 57
        mov     ah, 2Ah                                        ;#61B5: B4 2A
        int     21h                                            ;#61B7: CD 21
        push    cx                                             ;#61B9: 51
        mov     cl, 4                                          ;#61BA: B1 04
        shl     dh, cl                                         ;#61BC: D2 E6
        mov     cl, 3                                          ;#61BE: B1 03
        shl     dl, cl                                         ;#61C0: D2 E2
        pop     ax                                             ;#61C2: 58
        sub     ax, 7BCh                                       ;#61C3: 2D BC 07
        mov     cx, 4                                          ;#61C6: B9 04 00
        shl     dh, 1                                          ;#61C9: D0 E6
        rcl     ax, 1                                          ;#61CB: D1 D0
        loop    61C9h                                          ;#61CD: E2 FA
        mov     cl, 5                                          ;#61CF: B1 05
        shl     dl, 1                                          ;#61D1: D0 E2
        rcl     ax, 1                                          ;#61D3: D1 D0
        loop    61D1h                                          ;#61D5: E2 FA
        push    ax                                             ;#61D7: 50
        mov     ah, 2Ch                                        ;#61D8: B4 2C
        int     21h                                            ;#61DA: CD 21
        mov     ax, cx                                         ;#61DC: 8B C1
        shl     al, 1                                          ;#61DE: D0 E0
        shl     al, 1                                          ;#61E0: D0 E0
        mov     cx, 3                                          ;#61E2: B9 03 00
        shl     al, 1                                          ;#61E5: D0 E0
        rcl     ah, 1                                          ;#61E7: D0 D4
        loop    61E5h                                          ;#61E9: E2 FA
        and     dl, 1Fh                                        ;#61EB: 80 E2 1F
        or      al, dh                                         ;#61EE: 0A C6
        mov     cx, ax                                         ;#61F0: 8B C8
        pop     dx                                             ;#61F2: 5A
        mov     ax, 5701h                                      ;#61F3: B8 01 57
        int     21h                                            ;#61F6: CD 21
        call    near 6176h                                     ;#61F8: E8 7B FF
        test    byte [4DC8h], 1                                ;#61FB: F6 06 C8 4D 01
        jz      short 6207h                                    ;#6200: 74 05
        mov     byte [4DC7h], 1                                ;#6202: C6 06 C7 4D 01
        clc                                                    ;#6207: F8
        ret                                                    ;#6208: C3
        mov     dx, 1A1h                                       ;#6209: BA A1 01
        call    near 39FDh                                     ;#620C: E8 EE D7
        stc                                                    ;#620F: F9
        ret                                                    ;#6210: C3
        mov     al, [4DC8h]                                    ;#6211: A0 C8 4D
        test    byte [4DC4h], 80h                              ;#6214: F6 06 C4 4D 80
        jnz     short 623Bh                                    ;#6219: 75 20
        test    al, 1                                          ;#621B: A8 01
        jz      short 6289h                                    ;#621D: 74 6A
        test    al, 2                                          ;#621F: A8 02
        jnz     short 6289h                                    ;#6221: 75 66
        or      byte [es:4DC4h], 8                             ;#6223: 26 80 0E C4 4D 08
        call    near 5F94h                                     ;#6229: E8 68 FD
        jb      short 6289h                                    ;#622C: 72 5B
        call    near 62DBh                                     ;#622E: E8 AA 00
        jnz     short 6286h                                    ;#6231: 75 53
        mov     dx, 0B3Fh                                      ;#6233: BA 3F 0B
        call    near 39FDh                                     ;#6236: E8 C4 D7
        jmp     short 6211h                                    ;#6239: EB D6
        test    al, 2                                          ;#623B: A8 02
        jnz     short 6262h                                    ;#623D: 75 23
        test    al, 1                                          ;#623F: A8 01
        jz      short 6248h                                    ;#6241: 74 05
        call    near 5F94h                                     ;#6243: E8 4E FD
        jnb     short 622Eh                                    ;#6246: 73 E6
        call    near 5E63h                                     ;#6248: E8 18 FC
        jb      short 628Ch                                    ;#624B: 72 3F
        jz      short 6289h                                    ;#624D: 74 3A
        test    byte [4DC8h], 1                                ;#624F: F6 06 C8 4D 01
        jnz     short 625Bh                                    ;#6254: 75 05
        call    near 60CDh                                     ;#6256: E8 74 FE
        jnb     short 622Eh                                    ;#6259: 73 D3
        call    near 6036h                                     ;#625B: E8 D8 FD
        jb      short 6211h                                    ;#625E: 72 B1
        jmp     short 622Eh                                    ;#6260: EB CC
        test    al, 1                                          ;#6262: A8 01
        jnz     short 626Dh                                    ;#6264: 75 07
        and     byte [4DC8h], 0FDh                             ;#6266: 80 26 C8 4D FD
        jmp     short 6248h                                    ;#626B: EB DB
        call    near 5E63h                                     ;#626D: E8 F3 FB
        jb      short 628Ch                                    ;#6270: 72 1A
        jz      short 6289h                                    ;#6272: 74 15
        mov     si, [4DCFh]                                    ;#6274: 8B 36 CF 4D
        mov     di, [4DD1h]                                    ;#6278: 8B 3E D1 4D
        call    near 5D47h                                     ;#627C: E8 C8 FA
        call    near 5F83h                                     ;#627F: E8 01 FD
        jb      short 6211h                                    ;#6282: 72 8D
        jmp     short 622Eh                                    ;#6284: EB A8
        mov     al, 1                                          ;#6286: B0 01
        ret                                                    ;#6288: C3
        xor     al, al                                         ;#6289: 32 C0
        ret                                                    ;#628B: C3
        call    near 64E3h                                     ;#628C: E8 54 02
        call    near 6176h                                     ;#628F: E8 E4 FE
        call    near 6167h                                     ;#6292: E8 D2 FE
        and     byte [4DEDh], 0FCh                             ;#6295: 80 26 ED 4D FC
        mov     al, 0FFh                                       ;#629A: B0 FF
        ret                                                    ;#629C: C3
        push    cx                                             ;#629D: 51
        sub     [es:4DD4h], cx                                 ;#629E: 26 29 0E D4 4D
        jnb     short 62AAh                                    ;#62A3: 73 05
        dec     word [es:4DD6h]                                ;#62A5: 26 FF 0E D6 4D
        add     dx, cx                                         ;#62AA: 03 D1
        cmp     dx, 0FFFFh                                     ;#62AC: 83 FA FF
        jz      short 62CEh                                    ;#62AF: 74 1D
        cmp     cx, 0FFFFh                                     ;#62B1: 83 F9 FF
        jz      short 62BDh                                    ;#62B4: 74 07
        sub     [es:4DD8h], cx                                 ;#62B6: 26 29 0E D8 4D
        jnb     short 62C2h                                    ;#62BB: 73 05
        dec     word [es:4DDAh]                                ;#62BD: 26 FF 0E DA 4D
        mov     [es:4DDEh], dx                                 ;#62C2: 26 89 16 DE 4D
        mov     [es:4DDCh], ds                                 ;#62C7: 26 8C 1E DC 4D
        pop     cx                                             ;#62CC: 59
        ret                                                    ;#62CD: C3
        xor     dx, dx                                         ;#62CE: 33 D2
        call    near 609Fh                                     ;#62D0: E8 CC FD
        cmp     cx, 0FFFFh                                     ;#62D3: 83 F9 FF
        jz      short 62BDh                                    ;#62D6: 74 E5
        inc     cx                                             ;#62D8: 41
        jmp     short 62B6h                                    ;#62D9: EB DB
        call    near 62F8h                                     ;#62DB: E8 1A 00
        mov     si, 4B89h                                      ;#62DE: BE 89 4B
        mov     di, 4C09h                                      ;#62E1: BF 09 4C
        jb      short 62ECh                                    ;#62E4: 72 06
        mov     si, 4C89h                                      ;#62E6: BE 89 4C
        mov     di, 4D09h                                      ;#62E9: BF 09 4D
        cmpsb                                                  ;#62EC: A6
        jnz     short 62F7h                                    ;#62ED: 75 08
        cmp     byte [si], 0                                   ;#62EF: 80 3C 00
        jnz     short 62ECh                                    ;#62F2: 75 F8
        cmp     byte [di], 0                                   ;#62F4: 80 3D 00
        ret                                                    ;#62F7: C3
        test    byte [4DC5h], 1                                ;#62F8: F6 06 C5 4D 01
        jnz     short 6321h                                    ;#62FD: 75 22
        mov     si, 4C09h                                      ;#62FF: BE 09 4C
        mov     di, 4D09h                                      ;#6302: BF 09 4D
        mov     ah, 60h                                        ;#6305: B4 60
        int     21h                                            ;#6307: CD 21
        jb      short 6321h                                    ;#6309: 72 16
        mov     al, [4663h]                                    ;#630B: A0 63 46
        cmp     [di], al                                       ;#630E: 38 05
        jz      short 631Ah                                    ;#6310: 74 08
        cmp     byte [di], 0                                   ;#6312: 80 3D 00
        jz      short 6321h                                    ;#6315: 74 0A
        inc     di                                             ;#6317: 47
        jmp     short 630Eh                                    ;#6318: EB F4
        inc     di                                             ;#631A: 47
        mov     [4DD1h], di                                    ;#631B: 89 3E D1 4D
        jmp     short 630Eh                                    ;#631F: EB ED
        test    byte [4DC4h], 4                                ;#6321: F6 06 C4 4D 04
        jnz     short 6333h                                    ;#6326: 75 0B
        mov     si, 4B89h                                      ;#6328: BE 89 4B
        mov     di, 4C89h                                      ;#632B: BF 89 4C
        mov     ah, 60h                                        ;#632E: B4 60
        int     21h                                            ;#6330: CD 21
        ret                                                    ;#6332: C3
        stc                                                    ;#6333: F9
        ret                                                    ;#6334: C3
        call    near 60CDh                                     ;#6335: E8 95 FD
        jnb     short 633Dh                                    ;#6338: 73 03
        jmp     short 63B0h                                    ;#633A: EB 74
        nop                                                    ;#633C: 90
        call    near 6606h                                     ;#633D: E8 C6 02
        jnb     short 6345h                                    ;#6340: 73 03
        jmp     short 63AFh                                    ;#6342: EB 6B
        nop                                                    ;#6344: 90
        mov     bx, [4DE2h]                                    ;#6345: 8B 1E E2 4D
        call    near 63CBh                                     ;#6349: E8 7F 00
        jnb     short 6355h                                    ;#634C: 73 07
        test    byte [4DC5h], 1                                ;#634E: F6 06 C5 4D 01
        jz      short 63AFh                                    ;#6353: 74 5A
        cmp     byte [4DC6h], 0                                ;#6355: 80 3E C6 4D 00
        jnz     short 63C3h                                    ;#635A: 75 67
        call    near 6176h                                     ;#635C: E8 17 FE
        jb      short 63AFh                                    ;#635F: 72 4E
        and     byte [4DEDh], 0FEh                             ;#6361: 80 26 ED 4D FE
        mov     dx, 4C09h                                      ;#6366: BA 09 4C
        call    near 611Dh                                     ;#6369: E8 B1 FD
        jb      short 63AFh                                    ;#636C: 72 41
        call    near 6211h                                     ;#636E: E8 A0 FE
        cmp     al, 0                                          ;#6371: 3C 00
        jnle    short 6335h                                    ;#6373: 7F C0
        jl      short 63C1h                                    ;#6375: 7C 4A
        call    near 64E3h                                     ;#6377: E8 69 01
        jb      short 63AFh                                    ;#637A: 72 33
        xor     cx, cx                                         ;#637C: 33 C9
        call    near 6578h                                     ;#637E: E8 F7 01
        cmp     byte [4DC8h], 1                                ;#6381: 80 3E C8 4D 01
        jz      short 63A4h                                    ;#6386: 74 1C
        test    byte [4DC4h], 8Ch                              ;#6388: F6 06 C4 4D 8C
        jnz     short 63A4h                                    ;#638D: 75 15
        test    word [4DF0h], 8                                ;#638F: F7 06 F0 4D 08 00
        jnz     short 63A4h                                    ;#6395: 75 0D
        mov     cx, [4DE8h]                                    ;#6397: 8B 0E E8 4D
        mov     dx, [4DEAh]                                    ;#639B: 8B 16 EA 4D
        mov     ax, 5701h                                      ;#639F: B8 01 57
        int     21h                                            ;#63A2: CD 21
        call    near 6167h                                     ;#63A4: E8 C0 FD
        jb      short 63AFh                                    ;#63A7: 72 06
        and     byte [4DEDh], 0FDh                             ;#63A9: 80 26 ED 4D FD
        clc                                                    ;#63AE: F8
        ret                                                    ;#63AF: C3
        test    byte [4DC4h], 80h                              ;#63B0: F6 06 C4 4D 80
        jnz     short 636Eh                                    ;#63B5: 75 B7
        test    byte [4DC8h], 1                                ;#63B7: F6 06 C8 4D 01
        jnz     short 636Eh                                    ;#63BC: 75 B0
        call    near 5D3Ch                                     ;#63BE: E8 7B F9
        stc                                                    ;#63C1: F9
        ret                                                    ;#63C2: C3
        call    near 64E3h                                     ;#63C3: E8 1D 01
        jb      short 63AFh                                    ;#63C6: 72 E7
        jmp     near 6345h                                     ;#63C8: E9 7A FF
        push    ds                                             ;#63CB: 1E
        mov     dx, [es:4DDEh]                                 ;#63CC: 26 8B 16 DE 4D
        mov     ds, [es:4DDCh]                                 ;#63D1: 26 8E 1E DC 4D
        test    byte [es:4DC4h], 4                             ;#63D6: 26 F6 06 C4 4D 04
        jnz     short 6409h                                    ;#63DC: 75 2B
        mov     ax, [es:4DDAh]                                 ;#63DE: 26 A1 DA 4D
        mov     cx, [es:4DD6h]                                 ;#63E2: 26 8B 0E D6 4D
        or      dx, dx                                         ;#63E7: 0B D2
        jnz     short 642Eh                                    ;#63E9: 75 43
        or      cx, cx                                         ;#63EB: 0B C9
        jz      short 6409h                                    ;#63ED: 74 1A
        or      ax, ax                                         ;#63EF: 0B C0
        jz      short 645Ah                                    ;#63F1: 74 67
        mov     cx, 0FFFFh                                     ;#63F3: B9 FF FF
        call    near 6479h                                     ;#63F6: E8 80 00
        jb      short 642Ch                                    ;#63F9: 72 31
        cmp     cx, 0FFFFh                                     ;#63FB: 83 F9 FF
        jnz     short 642Bh                                    ;#63FE: 75 2B
        dec     ax                                             ;#6400: 48
        cmp     word [es:4DD6h], 0                             ;#6401: 26 83 3E D6 4D 00
        jnz     short 63EFh                                    ;#6407: 75 E6
        mov     cx, [es:4DD4h]                                 ;#6409: 26 8B 0E D4 4D
        mov     ax, [es:4DD8h]                                 ;#640E: 26 A1 D8 4D
        cmp     ax, cx                                         ;#6412: 3B C1
        jnb     short 6426h                                    ;#6414: 73 10
        cmp     word [es:4DDAh], 0                             ;#6416: 26 83 3E DA 4D 00
        jnz     short 6426h                                    ;#641C: 75 08
        mov     byte [es:4DC6h], 1                             ;#641E: 26 C6 06 C6 4D 01
        mov     cx, ax                                         ;#6424: 8B C8
        call    near 6479h                                     ;#6426: E8 50 00
        jb      short 642Ch                                    ;#6429: 72 01
        clc                                                    ;#642B: F8
        pop     ds                                             ;#642C: 1F
        ret                                                    ;#642D: C3
        push    dx                                             ;#642E: 52
        not     dx                                             ;#642F: F7 D2
        or      ax, ax                                         ;#6431: 0B C0
        jz      short 6467h                                    ;#6433: 74 32
        mov     cx, [es:4DD4h]                                 ;#6435: 26 8B 0E D4 4D
        cmp     dx, cx                                         ;#643A: 3B D1
        jb      short 6449h                                    ;#643C: 72 0B
        cmp     word [es:4DD6h], 0                             ;#643E: 26 83 3E D6 4D 00
        jnz     short 6449h                                    ;#6444: 75 03
        pop     dx                                             ;#6446: 5A
        jmp     short 6426h                                    ;#6447: EB DD
        mov     cx, dx                                         ;#6449: 8B CA
        pop     dx                                             ;#644B: 5A
        push    cx                                             ;#644C: 51
        call    near 6479h                                     ;#644D: E8 29 00
        pop     dx                                             ;#6450: 5A
        jb      short 642Ch                                    ;#6451: 72 D9
        cmp     cx, dx                                         ;#6453: 3B CA
        jnz     short 642Bh                                    ;#6455: 75 D4
        jmp     near 63CCh                                     ;#6457: E9 72 FF
        mov     byte [es:4DC6h], 1                             ;#645A: 26 C6 06 C6 4D 01
        mov     cx, [es:4DD8h]                                 ;#6460: 26 8B 0E D8 4D
        jmp     short 6426h                                    ;#6465: EB BF
        mov     ax, [es:4DD8h]                                 ;#6467: 26 A1 D8 4D
        cmp     ax, dx                                         ;#646B: 3B C2
        jnbe    short 6435h                                    ;#646D: 77 C6
        mov     cx, ax                                         ;#646F: 8B C8
        mov     byte [es:4DC6h], 1                             ;#6471: 26 C6 06 C6 4D 01
        jmp     short 6446h                                    ;#6477: EB CD
        push    ax                                             ;#6479: 50
        test    byte [es:4DC4h], 4                             ;#647A: 26 F6 06 C4 4D 04
        jz      short 64ABh                                    ;#6480: 74 29
        xor     di, di                                         ;#6482: 33 FF
        push    dx                                             ;#6484: 52
        push    ds                                             ;#6485: 1E
        mov     cx, 80h                                        ;#6486: B9 80 00
        mov     ah, 3Fh                                        ;#6489: B4 3F
        int     21h                                            ;#648B: CD 21
        or      ax, ax                                         ;#648D: 0B C0
        jz      short 64A0h                                    ;#648F: 74 0F
        mov     cx, ax                                         ;#6491: 8B C8
        call    near 65D1h                                     ;#6493: E8 3B 01
        pushf                                                  ;#6496: 9C
        add     di, cx                                         ;#6497: 03 F9
        add     dx, cx                                         ;#6499: 03 D1
        jb      short 64A6h                                    ;#649B: 72 09
        popf                                                   ;#649D: 9D
        jnb     short 6486h                                    ;#649E: 73 E6
        mov     cx, di                                         ;#64A0: 8B CF
        pop     ds                                             ;#64A2: 1F
        pop     dx                                             ;#64A3: 5A
        jmp     short 64D0h                                    ;#64A4: EB 2A
        call    near 609Fh                                     ;#64A6: E8 F6 FB
        jmp     short 649Dh                                    ;#64A9: EB F2
        mov     ah, 3Fh                                        ;#64AB: B4 3F
        int     21h                                            ;#64AD: CD 21
        jb      short 64D6h                                    ;#64AF: 72 25
        cmp     cx, ax                                         ;#64B1: 3B C8
        jnz     short 64D6h                                    ;#64B3: 75 21
        test    byte [es:4DC4h], 2                             ;#64B5: 26 F6 06 C4 4D 02
        jnz     short 64D0h                                    ;#64BB: 75 13
        cmp     byte [es:4DC8h], 1                             ;#64BD: 26 80 3E C8 4D 01
        jz      short 64CDh                                    ;#64C3: 74 08
        test    byte [es:4DC4h], 89h                           ;#64C5: 26 F6 06 C4 4D 89
        jz      short 64D0h                                    ;#64CB: 74 03
        call    near 65D1h                                     ;#64CD: E8 01 01
        call    near 629Dh                                     ;#64D0: E8 CA FD
        clc                                                    ;#64D3: F8
        pop     ax                                             ;#64D4: 58
        ret                                                    ;#64D5: C3
        push    ds                                             ;#64D6: 1E
        push    cs                                             ;#64D7: 0E
        pop     ds                                             ;#64D8: 1F
        mov     dx, 0A43h                                      ;#64D9: BA 43 0A
        call    near 4C07h                                     ;#64DC: E8 28 E7
        pop     ds                                             ;#64DF: 1F
        stc                                                    ;#64E0: F9
        jmp     short 64D4h                                    ;#64E1: EB F1
        mov     dx, 4C09h                                      ;#64E3: BA 09 4C
        call    near 611Dh                                     ;#64E6: E8 34 FC
        jb      short 6558h                                    ;#64E9: 72 6D
        push    ds                                             ;#64EB: 1E
        call    near 607Ch                                     ;#64EC: E8 8D FB
        cmp     byte [4DC6h], 0                                ;#64EF: 80 3E C6 4D 00
        jz      short 6560h                                    ;#64F4: 74 6A
        mov     [4DDCh], dx                                    ;#64F6: 89 16 DC 4D
        mov     word [4DDEh], 0                                ;#64FA: C7 06 DE 4D 00 00
        mov     ds, dx                                         ;#6500: 8E DA
        mov     bx, [es:4DE4h]                                 ;#6502: 26 8B 1E E4 4D
        mov     cx, [es:4DDAh]                                 ;#6507: 26 8B 0E DA 4D
        jcxz    651Dh                                          ;#650C: E3 0F
        push    cx                                             ;#650E: 51
        mov     cx, 0FFFFh                                     ;#650F: B9 FF FF
        call    near 6578h                                     ;#6512: E8 63 00
        pop     cx                                             ;#6515: 59
        jb      short 6558h                                    ;#6516: 72 40
        call    near 609Fh                                     ;#6518: E8 84 FB
        loop    650Eh                                          ;#651B: E2 F1
        mov     cx, [es:4DD8h]                                 ;#651D: 26 8B 0E D8 4D
        cmp     byte [es:4DC6h], 0                             ;#6522: 26 80 3E C6 4D 00
        jnz     short 6555h                                    ;#6528: 75 2B
        mov     al, [es:4DC4h]                                 ;#652A: 26 A0 C4 4D
        test    al, 20h                                        ;#652E: A8 20
        jnz     short 6555h                                    ;#6530: 75 23
        test    al, 10h                                        ;#6532: A8 10
        jnz     short 654Dh                                    ;#6534: 75 17
        mov     ah, [es:4DECh]                                 ;#6536: 26 8A 26 EC 4D
        test    ah, 2                                          ;#653B: F6 C4 02
        jnz     short 6555h                                    ;#653E: 75 15
        test    ah, 9                                          ;#6540: F6 C4 09
        jnz     short 654Dh                                    ;#6543: 75 08
        test    al, 2                                          ;#6545: A8 02
        jnz     short 6555h                                    ;#6547: 75 0C
        test    al, 89h                                        ;#6549: A8 89
        jz      short 6555h                                    ;#654B: 74 08
        xchg    cx, si                                         ;#654D: 87 F1
        mov     byte [si], 1Ah                                 ;#654F: C6 04 1A
        xchg    si, cx                                         ;#6552: 87 CE
        inc     cx                                             ;#6554: 41
        call    near 6578h                                     ;#6555: E8 20 00
        pop     ds                                             ;#6558: 1F
        mov     byte [es:4DC6h], 0                             ;#6559: 26 C6 06 C6 4D 00
        ret                                                    ;#655F: C3
        mov     bx, [4DDCh]                                    ;#6560: 8B 1E DC 4D
        sub     bx, dx                                         ;#6564: 2B DA
        mov     cl, 0Ch                                        ;#6566: B1 0C
        shr     bx, cl                                         ;#6568: D3 EB
        mov     [4DDAh], bx                                    ;#656A: 89 1E DA 4D
        mov     bx, [4DDEh]                                    ;#656E: 8B 1E DE 4D
        mov     [4DD8h], bx                                    ;#6572: 89 1E D8 4D
        jmp     short 6500h                                    ;#6576: EB 88
        push    ax                                             ;#6578: 50
        push    ds                                             ;#6579: 1E
        xor     dx, dx                                         ;#657A: 33 D2
        mov     ah, 40h                                        ;#657C: B4 40
        int     21h                                            ;#657E: CD 21
        push    cs                                             ;#6580: 0E
        pop     ds                                             ;#6581: 1F
        mov     dx, 0A68h                                      ;#6582: BA 68 0A
        jb      short 65B4h                                    ;#6585: 72 2D
        cmp     cx, ax                                         ;#6587: 3B C8
        jz      short 65CEh                                    ;#6589: 74 43
        test    byte [4DC5h], 1                                ;#658B: F6 06 C5 4D 01
        mov     dx, 0A8Dh                                      ;#6590: BA 8D 0A
        mov     byte [4DEFh], 1                                ;#6593: C6 06 EF 4D 01
        jz      short 65B4h                                    ;#6598: 74 1A
        mov     byte [4DEFh], 0                                ;#659A: C6 06 EF 4D 00
        inc     ax                                             ;#659F: 40
        cmp     cx, ax                                         ;#65A0: 3B C8
        jz      short 65CEh                                    ;#65A2: 74 2A
        mov     dx, 0AA3h                                      ;#65A4: BA A3 0A
        call    near 4C07h                                     ;#65A7: E8 5D E6
        call    near 6167h                                     ;#65AA: E8 BA FB
        and     byte [4DEDh], 0FDh                             ;#65AD: 80 26 ED 4D FD
        jmp     short 65CDh                                    ;#65B2: EB 19
        cmp     byte [4DEEh], 0                                ;#65B4: 80 3E EE 4D 00
        jnz     short 65CDh                                    ;#65B9: 75 12
        call    near 4C07h                                     ;#65BB: E8 49 E6
        call    near 6167h                                     ;#65BE: E8 A6 FB
        and     byte [4DEDh], 0FDh                             ;#65C1: 80 26 ED 4D FD
        mov     ah, 41h                                        ;#65C6: B4 41
        mov     dx, 4C09h                                      ;#65C8: BA 09 4C
        int     21h                                            ;#65CB: CD 21
        stc                                                    ;#65CD: F9
        pop     ds                                             ;#65CE: 1F
        pop     ax                                             ;#65CF: 58
        ret                                                    ;#65D0: C3
        push    es                                             ;#65D1: 06
        push    di                                             ;#65D2: 57
        push    cx                                             ;#65D3: 51
        mov     di, dx                                         ;#65D4: 8B FA
        push    ds                                             ;#65D6: 1E
        pop     es                                             ;#65D7: 07
        mov     al, 1Ah                                        ;#65D8: B0 1A
        repne   scasb                                          ;#65DA: F2 AE
        pop     cx                                             ;#65DC: 59
        clc                                                    ;#65DD: F8
        jnz     short 65E6h                                    ;#65DE: 75 06
        dec     di                                             ;#65E0: 4F
        sub     di, dx                                         ;#65E1: 2B FA
        mov     cx, di                                         ;#65E3: 8B CF
        stc                                                    ;#65E5: F9
        pop     di                                             ;#65E6: 5F
        pop     es                                             ;#65E7: 07
        ret                                                    ;#65E8: C3
        mov     dx, 531h                                       ;#65E9: BA 31 05
        call    near 39EEh                                     ;#65EC: E8 FF D3
        mov     dx, 4B89h                                      ;#65EF: BA 89 4B
        mov     al, [cs:4706h]                                 ;#65F2: 2E A0 06 47
        add     al, 41h                                        ;#65F6: 04 41
        cmp     [4B89h], al                                    ;#65F8: 38 06 89 4B
        jnz     short 6600h                                    ;#65FC: 75 02
        inc     dx                                             ;#65FE: 42
        inc     dx                                             ;#65FF: 42
        call    near 39E4h                                     ;#6600: E8 E1 D3
        jmp     near 3AD6h                                     ;#6603: E9 D0 D4
        mov     ax, 4400h                                      ;#6606: B8 00 44
        mov     bx, [4DE2h]                                    ;#6609: 8B 1E E2 4D
        int     21h                                            ;#660D: CD 21
        test    dl, 80h                                        ;#660F: F6 C2 80
        jz      short 6628h                                    ;#6612: 74 14
        test    byte [4DC3h], 2                                ;#6614: F6 06 C3 4D 02
        jz      short 6623h                                    ;#6619: 74 08
        mov     dx, 0AFEh                                      ;#661B: BA FE 0A
        call    near 4C07h                                     ;#661E: E8 E6 E5
        stc                                                    ;#6621: F9
        ret                                                    ;#6622: C3
        or      byte [4DC4h], 4                                ;#6623: 80 0E C4 4D 04
        clc                                                    ;#6628: F8
        ret                                                    ;#6629: C3
        cmp     al, 20h                                        ;#662A: 3C 20
        jz      short 6640h                                    ;#662C: 74 12
        cmp     al, 9                                          ;#662E: 3C 09
        jz      short 6640h                                    ;#6630: 74 0E
        cmp     al, 2Ch                                        ;#6632: 3C 2C
        jz      short 6640h                                    ;#6634: 74 0A
        cmp     al, 3Bh                                        ;#6636: 3C 3B
        jz      short 6640h                                    ;#6638: 74 06
        cmp     al, 3Ah                                        ;#663A: 3C 3A
        jz      short 6640h                                    ;#663C: 74 02
        cmp     al, 3Dh                                        ;#663E: 3C 3D
        ret                                                    ;#6640: C3
        mov     si, 4979h                                      ;#6641: BE 79 49
        mov     dl, [4C09h]                                    ;#6644: 8A 16 09 4C
        mov     [4979h], dl                                    ;#6648: 88 16 79 49
        mov     byte [497Ah], 3Ah                              ;#664C: C6 06 7A 49 3A
        call    near 666Bh                                     ;#6651: E8 17 00
        mov     ah, 3Bh                                        ;#6654: B4 3B
        mov     dx, 4C09h                                      ;#6656: BA 09 4C
        int     21h                                            ;#6659: CD 21
        mov     al, 0                                          ;#665B: B0 00
        jb      short 6661h                                    ;#665D: 72 02
        inc     al                                             ;#665F: FE C0
        push    ax                                             ;#6661: 50
        mov     ah, 3Bh                                        ;#6662: B4 3B
        mov     dx, 4979h                                      ;#6664: BA 79 49
        int     21h                                            ;#6667: CD 21
        pop     ax                                             ;#6669: 58
        ret                                                    ;#666A: C3
        mov     dl, [si]                                       ;#666B: 8A 14
        mov     al, [4663h]                                    ;#666D: A0 63 46
        mov     [si+2], al                                     ;#6670: 88 44 02
        sub     dl, 40h                                        ;#6673: 80 EA 40
        mov     ah, 47h                                        ;#6676: B4 47
        inc     si                                             ;#6678: 46
        inc     si                                             ;#6679: 46
        inc     si                                             ;#667A: 46
        int     21h                                            ;#667B: CD 21
        ret                                                    ;#667D: C3
        db      134 dup (0)
        and     [bx+si], al                                    ;#6704: 20 00
        or      ax, 0                                          ;#6706: 0D 00 00
        db      506 dup (0)
        inc     word [bx+si]                                   ;#6903: FF 00
        db      219 dup (0)
        pop     es                                             ;#69E0: 07
        db      306 dup (0)
        inc     word [bx+si]                                   ;#6B13: FF 00
        db      767 dup (0)
        inc     word [bx+si]                                   ;#6E14: FF 00
        add     [bx+si], al                                    ;#6E16: 00 00
        add     [bx+si], al                                    ;#6E18: 00 00
        or      [bx+si], al                                    ;#6E1A: 08 00

FCB_WILDCARD_NAME:
        ; "???????????"
        ; Format: FORMAT_STRING
        db      "???????????"                                  ;#6E1C: 3F 3F 3F 3F 3F 3F 3F 3F 3F 3F 3F
        db      361 dup (0)

END_POINTER:
        end
