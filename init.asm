; SISNE (PC/8086, SCOPUS, 1983) — disk 1 init (LBA 12, first data sector loaded by the boot)
; Disassembled by Ricardo Bittencourt (bluepenguin@gmail.com)
; Last update at 2026-07-31
;
        .8086
        .model tiny
        .code
        org 00000h


        jmp     short INIT_ENTRY                               ;#0000: EB 1A
        nop                                                    ;#0002: 90

BPB_BYTES_PER_SECTOR:
        ; Bytes per sector (= 0200h) — at BPB+0 (vs boot BPB+0x0B)
        dw      200h                                           ;#0003: 00 02

BPB_SECTORS_PER_CLUSTER:
        ; Sectors per cluster (= 2 → 1 KB clusters)
        db      2                                              ;#0005: 02

BPB_RESERVED_SECTORS:
        ; Reserved sectors before the first FAT (the boot sector itself)
        dw      1                                              ;#0006: 01 00

BPB_FAT_COUNT:
        ; Number of FAT copies (= 2)
        db      2                                              ;#0008: 02

BPB_ROOT_ENTRIES:
        ; Root directory entry count (= 112) — also re-used as "entries remaining" counter
        dw      0070h                                          ;#0009: 70 00

BPB_TOTAL_SECTORS:
        ; Total sectors on disk (= 0x02D0 = 720)
        dw      2D0h                                           ;#000B: D0 02

BPB_MEDIA_DESCRIPTOR:
        ; Media type byte (= FDh, 5.25" DSDD 360 KB)
        db      0FDh                                           ;#000D: FD

BPB_SECTORS_PER_FAT:
        ; FAT length in sectors (= 2)
        dw      2                                              ;#000E: 02 00

BPB_SECTORS_PER_TRACK:
        ; Geometry — sectors per track (= 9)
        dw      9                                              ;#0010: 09 00

BPB_HEAD_COUNT:
        ; Geometry — number of heads (= 2)
        dw      2                                              ;#0012: 02 00

BPB_HIDDEN_SECTORS:
        ; Hidden sector count (dword) — 0 on a floppy
        dd      0                                              ;#0014: 00 00 00 00
        dw      0                                              ;#0018: 00 00

INIT_DRIVE_NUMBER:
        ; Drive ID byte — read into DL just before far-JMPing to the loaded program
        db      0                                              ;#001A: 00
        db      0                                              ;#001B: 00

INIT_ENTRY:
ROOT_LBA:
        ; Runtime-written dword (low word) — LBA of the first root-directory sector
        ; The bytes here are the first instructions of the bootstrap; once execution
        ; passes them, the same bytes are written as the runtime ROOT_LBA dword.
        mov     [BOOT_LBA_TO_CHS_FAR_OFF], bx                  ;#001C: 89 1E EA 01
SECTOR_BUFFER_COUNT:
        ; Scratch byte — sector-batch counter / FAT byte saved during cluster walk
        mov     [BOOT_LBA_TO_CHS_FAR_SEG], ax                  ;#0020: A3 EC 01
        mov     [BOOT_MSG_OFFSET], cx                          ;#0023: 89 0E EE 01
        mov     [BOOT_MSG_SEGMENT], ax                         ;#0027: A3 F0 01
        mov     ax, 70h                                        ;#002A: B8 70 00
        mov     es, ax                                         ;#002D: 8E C0
        mov     al, [BPB_FAT_COUNT]                            ;#002F: A0 08 00
        cbw                                                    ;#0032: 98
        mul     word [BPB_SECTORS_PER_FAT]                     ;#0033: F7 26 0E 00
        add     ax, [BPB_RESERVED_SECTORS]                     ;#0037: 03 06 06 00
        add     ax, [BPB_HIDDEN_SECTORS]                       ;#003B: 03 06 14 00
        adc     dx, [BPB_HIDDEN_SECTORS+2]                     ;#003F: 13 16 16 00
        mov     [ROOT_LBA], ax                                 ;#0043: A3 1C 00
        mov     [ROOT_LBA+2], dx                               ;#0046: 89 16 1E 00
        push    ax                                             ;#004A: 50
        push    dx                                             ;#004B: 52
        mov     ax, 20h                                        ;#004C: B8 20 00
        mul     word [BPB_ROOT_ENTRIES]                        ;#004F: F7 26 09 00
        add     ax, 1FFh                                       ;#0053: 05 FF 01
        mov     bx, 200h                                       ;#0056: BB 00 02
        div     bx                                             ;#0059: F7 F3
        add     [ROOT_LBA], ax                                 ;#005B: 01 06 1C 00
        adc     word [ROOT_LBA+2], 0                           ;#005F: 83 16 1E 00 00
        pop     dx                                             ;#0064: 5A
        pop     ax                                             ;#0065: 58
READ_NEXT_BATCH:
        ; BP reached 0 — fall through to call far disk-helper for the next 8 sectors
        mov     bp, 80h                                        ;#0066: BD 80 00
        push    ax                                             ;#0069: 50
        push    dx                                             ;#006A: 52
        push    bp                                             ;#006B: 55
        mov     cl, 8                                          ;#006C: B1 08
        ; Far-call the boot's LBA_TO_CHS_FAR — read CL sectors from DX:AX (LBA) to ES:BX
        call    far word [BOOT_LBA_TO_CHS_FAR_OFF]             ;#006E: FF 1E EA 01
        pop     bp                                             ;#0072: 5D
        pop     dx                                             ;#0073: 5A
        pop     ax                                             ;#0074: 58
        add     ax, 8                                          ;#0075: 05 08 00
        xor     di, di                                         ;#0078: 33 FF
SCAN_DIR_ENTRIES:
        ; Loop top — check the current root-dir entry: 0 → end-of-dir, else compare name
        cmp     byte [es:di], 0                                ;#007A: 26 80 3D 00
        jnz     short COMPARE_FILENAME                         ;#007E: 75 13
SHOW_ERROR_AND_HANG:
        ; Print MSG_INVALID_DISK (offset/segment passed in by the boot), wait key, INT 19h
        mov     si, [BOOT_MSG_OFFSET]                          ;#0080: 8B 36 EE 01
        push    ds                                             ;#0084: 1E
        mov     ds, [BOOT_MSG_SEGMENT]                         ;#0085: 8E 1E F0 01
        call    near PRINT_LOOP                                ;#0089: E8 09 01
        pop     ds                                             ;#008C: 1F
        xor     ah, ah                                         ;#008D: 32 E4
        ; INT 16h AH=0 — wait for keystroke (used as "press any key to reboot")
        int     16h                                            ;#008F: CD 16
        ; INT 19h — restart bootstrap (reload sector 0 to 0000:7C00); does not return
        int     19h                                            ;#0091: CD 19
COMPARE_FILENAME:
        ; rep cmpsb against SISNE_FILENAME (11 bytes) for the current dir entry
        mov     si, SISNE_FILENAME                             ;#0093: BE F2 01
        mov     cx, 0Bh                                        ;#0096: B9 0B 00
        cld                                                    ;#0099: FC
        rep     cmpsb                                          ;#009A: F3 A6
        jz      short FILE_FOUND                               ;#009C: 74 10
        dec     word [BPB_ROOT_ENTRIES]                        ;#009E: FF 0E 09 00
        jz      short SHOW_ERROR_AND_HANG                      ;#00A2: 74 DC
        dec     bp                                             ;#00A4: 4D
        jz      short READ_NEXT_BATCH                          ;#00A5: 74 BF
        sub     cx, 0FFEBh                                     ;#00A7: 83 E9 EB
        add     di, cx                                         ;#00AA: 03 F9
        jmp     short SCAN_DIR_ENTRIES                         ;#00AC: EB CC

FILE_FOUND:
        ; Names matched — read the entry's first cluster, walk the FAT chain to load
        add     di, 0Fh                                        ;#00AE: 83 C7 0F
        push    word [es:di]                                   ;#00B1: 26 FF 35
        mov     al, [BPB_SECTORS_PER_FAT]                      ;#00B4: A0 0E 00
        mov     [SECTOR_BUFFER_COUNT], al                      ;#00B7: A2 20 00
        mov     ax, 2000h                                      ;#00BA: B8 00 20
        mov     es, ax                                         ;#00BD: 8E C0
        xor     dx, dx                                         ;#00BF: 33 D2
        mov     ax, [BPB_RESERVED_SECTORS]                     ;#00C1: A1 06 00
        add     ax, [BPB_HIDDEN_SECTORS]                       ;#00C4: 03 06 14 00
        adc     dx, [BPB_HIDDEN_SECTORS+2]                     ;#00C8: 13 16 16 00
        mov     cl, [SECTOR_BUFFER_COUNT]                      ;#00CC: 8A 0E 20 00
        push    ss                                             ;#00D0: 16
        pop     bx                                             ;#00D1: 5B
        call    near CHECK_READ_WITHIN_STACK                   ;#00D2: E8 FD 00
        jnb     short CALL_HELPER_PROBE                        ;#00D5: 73 02
        jmp     short SHOW_ERROR_AND_HANG                      ;#00D7: EB A7

CALL_HELPER_PROBE:
        ; No-overlap branch — far-call the boot helper for next sector
        ; Far-call boot's LBA_TO_CHS_FAR helper (= LBA→CHS + INT 13h read)
        call    far word [BOOT_LBA_TO_CHS_FAR_OFF]             ;#00D9: FF 1E EA 01
        mov     ax, 70h                                        ;#00DD: B8 70 00
        mov     es, ax                                         ;#00E0: 8E C0
        pop     bx                                             ;#00E2: 5B
AFTER_FIRST_READ:
        ; Re-enter loop with CL = saved sec_per_FAT byte; recompute LBA pieces
        mov     cl, [BPB_SECTORS_PER_CLUSTER]                  ;#00E3: 8A 0E 05 00
        xor     ch, ch                                         ;#00E7: 32 ED
        mov     [SECTOR_BUFFER_COUNT], cl                      ;#00E9: 88 0E 20 00
        mov     ax, bx                                         ;#00ED: 8B C3
        dec     ax                                             ;#00EF: 48
        dec     ax                                             ;#00F0: 48
        mul     cx                                             ;#00F1: F7 E1
        add     ax, [ROOT_LBA]                                 ;#00F3: 03 06 1C 00
        adc     dx, [ROOT_LBA+2]                               ;#00F7: 13 16 1E 00
        xchg    cl, ch                                         ;#00FB: 86 E9
WALK_FAT_CHAIN:
        ; Fetch the next FAT entry for the current cluster, decide if we keep loading
        push    ds                                             ;#00FD: 1E
        push    bx                                             ;#00FE: 53
        mov     si, 2000h                                      ;#00FF: BE 00 20
        mov     ds, si                                         ;#0102: 8E DE
        mov     si, bx                                         ;#0104: 8B F3
        shr     si, 1                                          ;#0106: D1 EE
        mov     bx, [bx+si]                                    ;#0108: 8B 18
        jnb     short MASK_CLUSTER_NUMBER                      ;#010A: 73 04
        mov     cl, 4                                          ;#010C: B1 04
        shr     bx, cl                                         ;#010E: D3 EB
MASK_CLUSTER_NUMBER:
        ; AND BX with 0FFFh — clip the FAT12 entry to 12 bits after extraction
        and     bx, 0FFFh                                      ;#0110: 81 E3 FF 0F
        pop     si                                             ;#0114: 5E
        pop     ds                                             ;#0115: 1F
        cmp     [SECTOR_BUFFER_COUNT], ch                      ;#0116: 38 2E 20 00
        jnz     short READ_CURRENT_CLUSTER                     ;#011A: 75 07
        xor     di, di                                         ;#011C: 33 FF
        call    near CHECK_FITS_BELOW_STACK                    ;#011E: E8 83 00
        jb      short NEXT_CLUSTER_RETRY                       ;#0121: 72 15
READ_CURRENT_CLUSTER:
        ; Issue the next disk read for this cluster via the boot's LBA_TO_CHS_FAR helper
        sub     si, bx                                         ;#0123: 2B F3
        cmp     si, 0FFFFh                                     ;#0125: 83 FE FF
        jnz     short LOAD_NEXT_FILE_CHUNK                     ;#0128: 75 3B
        mov     di, 1                                          ;#012A: BF 01 00
        call    near CHECK_FITS_BELOW_STACK                    ;#012D: E8 74 00
        jb      short LOAD_NEXT_FILE_CHUNK                     ;#0130: 72 33
        add     [SECTOR_BUFFER_COUNT], ch                      ;#0132: 00 2E 20 00
        jmp     short WALK_FAT_CHAIN                           ;#0136: EB C5

NEXT_CLUSTER_RETRY:
        ; Retry-friendly entry: push BX, recompute count from [SECTOR_BUFFER_COUNT]
        push    bx                                             ;#0138: 53
        mov     cl, [SECTOR_BUFFER_COUNT]                      ;#0139: 8A 0E 20 00
        mov     bx, 2000h                                      ;#013D: BB 00 20
        call    near CHECK_READ_WITHIN_STACK                   ;#0140: E8 8F 00
        jnb     short ADJUST_AND_COPY_TO_HIGH                  ;#0143: 73 03
        jmp     near SHOW_ERROR_AND_HANG                       ;#0145: E9 38 FF

ADJUST_AND_COPY_TO_HIGH:
        ; After a cluster read, shift ES forward and far-call the boot's helper again
        push    es                                             ;#0148: 06
        push    ss                                             ;#0149: 16
        pop     bx                                             ;#014A: 5B
        add     bx, 100h                                       ;#014B: 81 C3 00 01
        mov     es, bx                                         ;#014F: 8E C3
        ; Far-call the boot's LBA_TO_CHS_FAR — also used here after relocating ES
        call    far word [BOOT_LBA_TO_CHS_FAR_OFF]             ;#0151: FF 1E EA 01
        push    es                                             ;#0155: 06
        pop     ds                                             ;#0156: 1F
        pop     es                                             ;#0157: 07
        xor     di, di                                         ;#0158: 33 FF
        xor     si, si                                         ;#015A: 33 F6
        mov     cx, bx                                         ;#015C: 8B CB
        rep     movsb                                          ;#015E: F3 A4
        push    cs                                             ;#0160: 0E
        pop     ds                                             ;#0161: 1F
        jmp     short BUMP_ES_AND_CONTINUE                     ;#0162: EB 14
        nop                                                    ;#0164: 90

LOAD_NEXT_FILE_CHUNK:
        ; Tail of the cluster loop — fetch next cluster's data
        push    bx                                             ;#0165: 53
        mov     cl, [SECTOR_BUFFER_COUNT]                      ;#0166: 8A 0E 20 00
        push    ss                                             ;#016A: 16
        pop     bx                                             ;#016B: 5B
        call    near CHECK_READ_WITHIN_STACK                   ;#016C: E8 63 00
        jnb     short CALL_HELPER_LAST_CHUNK                   ;#016F: 73 03
        jmp     near SHOW_ERROR_AND_HANG                       ;#0171: E9 0C FF

CALL_HELPER_LAST_CHUNK:
        ; Tail of LOAD_NEXT_FILE_CHUNK — far-call the boot's helper again
        ; Far-call the boot's LBA_TO_CHS_FAR — last chunk read of the file
        call    far word [BOOT_LBA_TO_CHS_FAR_OFF]             ;#0174: FF 1E EA 01
BUMP_ES_AND_CONTINUE:
        ; Move ES forward by the cluster's paragraph size, then loop or finish
        mov     ax, es                                         ;#0178: 8C C0
        mov     cl, 4                                          ;#017A: B1 04
        shr     bx, cl                                         ;#017C: D3 EB
        add     ax, bx                                         ;#017E: 03 C3
        mov     es, ax                                         ;#0180: 8E C0
        pop     bx                                             ;#0182: 5B
        cmp     bx, 0FFFh                                      ;#0183: 81 FB FF 0F
        jz      short READ_DRIVE_AND_JUMP                      ;#0187: 74 03
        jmp     near AFTER_FIRST_READ                          ;#0189: E9 57 FF

READ_DRIVE_AND_JUMP:
        ; Drive number → DL, far-JMP to 70h:0 (the entry point of the loaded program)
        mov     dl, [INIT_DRIVE_NUMBER]                        ;#018C: 8A 16 1A 00
        ; Hand off to the loaded SISNE.SIS program at 70h:0 (= linear 700h)
        jmp     far 70h:0                                      ;#0190: EA 00 00 70 00

PRINT_LOOP:
        ; lodsb / and 7Fh / INT 10h teletype — same shape as the boot's PRINT_LOOP
        lodsb                                                  ;#0195: AC
        and     al, 7Fh                                        ;#0196: 24 7F
        jz      short PRINT_RET                                ;#0198: 74 09
        mov     ah, 0Eh                                        ;#019A: B4 0E
        mov     bx, 7                                          ;#019C: BB 07 00
        ; INT 10h AH=0Eh — teletype output; AL=char, BH=page (0), BL=color (7)
        int     10h                                            ;#019F: CD 10
        jmp     short PRINT_LOOP                               ;#01A1: EB F2

PRINT_RET:
        ; Shared `ret` for PRINT_LOOP and CHECK_FITS_BELOW_STACK
        ret                                                    ;#01A3: C3

CHECK_FITS_BELOW_STACK:
        ; Computes (ES + 0x1000 paragraph windows) and compares to a target — sets CF
        push    dx                                             ;#01A4: 52
        push    ax                                             ;#01A5: 50
        mov     al, [SECTOR_BUFFER_COUNT]                      ;#01A6: A0 20 00
        cbw                                                    ;#01A9: 98
        test    di, di                                         ;#01AA: 85 FF
        jz      short STACK_CHECK_MUL                          ;#01AC: 74 02
        add     al, ch                                         ;#01AE: 02 C5
STACK_CHECK_MUL:
        ; Inside CHECK_FITS_BELOW_STACK: multiply count by bytes_per_sector to get total
        mul     word [BPB_BYTES_PER_SECTOR]                    ;#01B0: F7 26 03 00
        jb      short STACK_CHECK_DONE                         ;#01B4: 72 19
        mov     dx, es                                         ;#01B6: 8C C2
        and     dx, 0F000h                                     ;#01B8: 81 E2 00 F0
        push    dx                                             ;#01BC: 52
        mov     cl, 4                                          ;#01BD: B1 04
        shr     ax, cl                                         ;#01BF: D3 E8
        mov     dx, es                                         ;#01C1: 8C C2
        add     ax, dx                                         ;#01C3: 03 C2
        and     ax, 0F000h                                     ;#01C5: 25 00 F0
        pop     dx                                             ;#01C8: 5A
        cmp     dx, ax                                         ;#01C9: 3B D0
        clc                                                    ;#01CB: F8
        jz      short STACK_CHECK_DONE                         ;#01CC: 74 01
        stc                                                    ;#01CE: F9
STACK_CHECK_DONE:
        ; Pop saved AX/DX and return — common tail of CHECK_FITS_BELOW_STACK
        pop     ax                                             ;#01CF: 58
        pop     dx                                             ;#01D0: 5A
        ret                                                    ;#01D1: C3

CHECK_READ_WITHIN_STACK:
        ; Sub: ES + CL*bytes_per_sec_paragraphs vs BX (= SS) — CF=1 if read would overflow
        push    dx                                             ;#01D2: 52
        push    cx                                             ;#01D3: 51
        push    ax                                             ;#01D4: 50
        mov     al, cl                                         ;#01D5: 8A C1
        cbw                                                    ;#01D7: 98
        mul     word [BPB_BYTES_PER_SECTOR]                    ;#01D8: F7 26 03 00
        mov     cl, 4                                          ;#01DC: B1 04
        shr     ax, cl                                         ;#01DE: D3 E8
        push    es                                             ;#01E0: 06
        pop     cx                                             ;#01E1: 59
        add     ax, cx                                         ;#01E2: 03 C1
        cmp     bx, ax                                         ;#01E4: 3B D8
        pop     ax                                             ;#01E6: 58
        pop     cx                                             ;#01E7: 59
        pop     dx                                             ;#01E8: 5A
        ret                                                    ;#01E9: C3

BOOT_LBA_TO_CHS_FAR_OFF:
        ; Saved BX from boot = offset of LBA_TO_CHS_FAR (0x017B) in boot segment
        dw      0                                              ;#01EA: 00 00

BOOT_LBA_TO_CHS_FAR_SEG:
        ; Saved AX from boot's handoff = boot's segment (where LBA_TO_CHS_FAR lives)
        dw      0                                              ;#01EC: 00 00

BOOT_MSG_OFFSET:
        ; Saved CX from boot's handoff = offset of MSG_INVALID_DISK in boot's segment
        dw      0                                              ;#01EE: 00 00

BOOT_MSG_SEGMENT:
        ; Saved AX again = boot's segment (same as +2, used for MSG too)
        dw      0                                              ;#01F0: 00 00

SISNE_FILENAME:
        ; 11-byte FAT12-style filename "SISNE   SIS" — the root-dir target
        db      "SISNE   SIS"                                  ;#01F2: 53 49 53 4E 45 20 20 ...
        times   3 db 0                                         ;#01FD: 00 00 00

END_POINTER:
        end
