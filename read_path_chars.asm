; ============================================================================
; READ_PATH_CHARS @ 0x0E00 in SISNE.SIS  (73 bytes, 8086)
;
; Select `drive` (cursor = `start`) then advance the FCB path cursor up to `n`
; characters, stopping early if it runs off the end (cursor 0 or past COUNT),
; in which case the cursor is parked at 0xFFFF. Returns the final cursor (AX).
;
; C source (compiled by tiny_cc to the bytes below):
;
;   int read_path_chars(unsigned char drive, int start, unsigned int n)
;   {
;       init_fcb_from_drive(drive, start);
;   loop:
;       if (n > 0) {
;           if (CURSOR != 0) {
;               if (CURSOR <= COUNT) goto body;
;           }
;           CURSOR = 0xFFFF;
;       }
;       return CURSOR;
;   body:
;       CURSOR = read_fcb_path_char(CURSOR);
;       n--;
;       goto loop;
;   }
;
; Stack frame:  [bp+4]=drive  [bp+6]=start  [bp+8]=n
; Globals:      CURSOR=0x1544  COUNT=0x1572
; Calls:        INIT_FCB_FROM_DRIVE=0x0C06   READ_FCB_PATH_CHAR=0xB791
; ============================================================================

CURSOR              equ 1544h
COUNT               equ 1572h
INIT_FCB_FROM_DRIVE equ 0C06h
READ_FCB_PATH_CHAR  equ 0B791h

                org 0E00h

READ_PATH_CHARS:
                push    bp                          ; 0E00: 55
                mov     bp, sp                      ; 0E01: 8B EC
                push    word [bp+6]                 ; 0E03: FF 76 06   start
                mov     al, [bp+4]                  ; 0E06: 8A 46 04   drive
                sub     ah, ah                      ; 0E09: 2A E4
                push    ax                          ; 0E0B: 50
                call    INIT_FCB_FROM_DRIVE         ; 0E0C: E8 F7 FD
                add     sp, 4                        ; 0E0F: 83 C4 04

.loop:                                              ; while top
                cmp     word [bp+8], 0              ; 0E12: 83 7E 08 00   n
                jbe     .return_cursor             ; 0E16: 76 16        n <= 0
                cmp     word [CURSOR], 0           ; 0E18: 83 3E 44 15 00
                jz      .end_mark                  ; 0E1D: 74 09        CURSOR == 0
                mov     ax, [COUNT]                ; 0E1F: A1 72 15
                cmp     [CURSOR], ax               ; 0E22: 39 06 44 15
                jbe     .body                      ; 0E26: 76 0B        CURSOR <= COUNT

.end_mark:
                mov     word [CURSOR], 0FFFFh      ; 0E28: C7 06 44 15 FF FF

.return_cursor:
                mov     ax, [CURSOR]               ; 0E2E: A1 44 15
                jmp     .ret                       ; 0E31: EB 12

.body:
                push    word [CURSOR]              ; 0E33: FF 36 44 15
                call    READ_FCB_PATH_CHAR         ; 0E37: E8 57 A9
                add     sp, 2                       ; 0E3A: 83 C4 02
                mov     [CURSOR], ax               ; 0E3D: A3 44 15
                dec     word [bp+8]                ; 0E40: FF 4E 08      n--
                jmp     .loop                      ; 0E43: EB CD

.ret:
                mov     sp, bp                      ; 0E45: 8B E5
                pop     bp                          ; 0E47: 5D
                ret                                 ; 0E48: C3
