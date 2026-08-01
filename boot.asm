; SISNE (PC/8086, SCOPUS, 1983) — disk 1 boot sector
; Disassembled by Ricardo Bittencourt (bluepenguin@gmail.com)
; Last update at 2026-08-01
;
        .8086
        .model tiny
        .code
        org 00000h

SECTORS_REMAINING_SCRATCH        equ     0002Eh    ; Sectors-left counter — byte inside `mov ds, ax` (safe after relocation)

INT_1E_VECTOR                    equ     00078h    ; IVT entry for INT 1Eh — far pointer to the active DPT (4 bytes at 0:0078)
DPT                              equ     00522h    ; RAM address of the relocated Disk Parameter Table (segment 0)
DPT_LAST_SECTOR                  equ     00526h    ; DPT[4] — last sector on a track (= DPT + 4)
DPT_HEAD_DELAY                   equ     0052Bh    ; DPT[9] — head settle delay in ms (= DPT + 9)

        jmp     short BOOTSTRAP                                ;#0000: EB 28
        nop                                                    ;#0002: 90

BPB:
        ; BIOS Parameter Block — OEM ID "4-(2yIHC" (8 bytes ASCII)
        db      "4-(2yIHC"                                     ;#0003: 34 2D 28 32 79 49 48 ...

BPB_BYTES_PER_SECTOR:
        ; Bytes per sector (512) — standard DOS BPB starts here
        dw      200h                                           ;#000B: 00 02

BPB_SECTORS_PER_CLUSTER:
        ; Sectors per cluster (2 → 1 KB clusters)
        db      2                                              ;#000D: 02

BPB_RESERVED_SECTORS:
        ; Reserved sectors before the first FAT (the boot itself)
        dw      1                                              ;#000E: 01 00

BPB_FAT_COUNT:
        ; Number of FAT copies on the disk
        db      2                                              ;#0010: 02

BPB_ROOT_ENTRIES:
        ; Root directory entry count (112)
        dw      0070h                                          ;#0011: 70 00

BPB_TOTAL_SECTORS:
        ; Total sectors on disk (720 = 360 KB)
        dw      2D0h                                           ;#0013: D0 02

BPB_MEDIA_DESCRIPTOR:
        ; Media type byte (FDh = 5.25" DSDD 360 KB)
        db      0FDh                                           ;#0015: FD

BPB_SECTORS_PER_FAT:
        ; FAT length in sectors
        dw      2                                              ;#0016: 02 00

BPB_SECTORS_PER_TRACK:
        ; Geometry: sectors per track (9)
        dw      9                                              ;#0018: 09 00

BPB_HEAD_COUNT:
        ; Geometry: number of heads (2)
        dw      2                                              ;#001A: 02 00

BPB_HIDDEN_SECTORS:
        ; Hidden-sector count (dword) — 0 on floppies
        dd      0                                              ;#001C: 00 00 00 00
        dw      0                                              ;#0020: 00 00

SISNE_DRIVE_NUMBER:
        ; Drive ID for INT 13 (low byte of the DX-pair)
        db      0                                              ;#0022: 00

SISNE_HEAD_NUMBER:
        ; Head byte — LBA_TO_CHS writes it so word-reading SISNE_DRIVE_NUMBER packs DL/DH
        db      0                                              ;#0023: 00

INITIAL_LBA_SECTOR:
        ; First disk sector to load (32-bit LBA); on disk 1 = 12 = first data cluster
        dd      0Ch                                            ;#0024: 0C 00 00 00
DPT_PATCH_LAST_SECTOR:
        ; Source byte — copied into [DPT_LAST_SECTOR] at runtime
        db      9                                              ;#0028: 09

DPT_PATCH_HEAD_DELAY:
        ; Source byte — copied into [DPT_HEAD_DELAY] at runtime
        db      1                                              ;#0029: 01

BOOTSTRAP:
        ; JMP target after BPB; loads DS=7C0h (the standard BIOS CS at boot, so DS=CS now)
        mov     ax, 7C0h                                       ;#002A: B8 C0 07
        mov     ds, ax                                         ;#002D: 8E D8
        ; INT 12h — return conventional memory size in KB in AX
        int     12h                                            ;#002F: CD 12
        mov     dx, ax                                         ;#0031: 8B D0
        mov     cl, 6                                          ;#0033: B1 06
        shl     dx, cl                                         ;#0035: D3 E2
        mov     ax, [BPB_BYTES_PER_SECTOR]                     ;#0037: A1 0B 00
        mov     cl, 4                                          ;#003A: B1 04
        shr     ax, cl                                         ;#003C: D3 E8
        mul     byte [BPB_SECTORS_PER_CLUSTER]                 ;#003E: F6 26 0D 00
        mov     bx, ax                                         ;#0042: 8B D8
        mov     cx, dx                                         ;#0044: 8B CA
        and     cx, 0FFFh                                      ;#0046: 81 E1 FF 0F
        add     ax, 140h                                       ;#004A: 05 40 01
        cmp     cx, ax                                         ;#004D: 3B C8
        jnb     short RELOCATE_TO_HIGH_MEM                     ;#004F: 73 04
        ; only when memory is tight (low 12 bits short) — rounds DX to a 64KB boundary
        and     dx, 0F000h                                     ;#0051: 81 E2 00 F0
RELOCATE_TO_HIGH_MEM:
        ; Always sub 20h (room for one-sector buffer below the boot copy)
        sub     dx, 20h                                        ;#0055: 83 EA 20
        mov     [FAR_LOADER_SEGMENT], dx                       ;#0058: 89 16 97 01
        cld                                                    ;#005C: FC
        mov     es, dx                                         ;#005D: 8E C2
        mov     di, 0                                          ;#005F: BF 00 00
        mov     si, di                                         ;#0062: 8B F7
        mov     cx, 200h                                       ;#0064: B9 00 02
        rep     movsb                                          ;#0067: F3 A4
        jmp     far word [FAR_LOADER_OFFSET]                   ;#0069: FF 2E 95 01
        cli                                                    ;#006D: FA
        sub     dx, 120h                                       ;#006E: 81 EA 20 01
        sub     dx, bx                                         ;#0072: 2B D3
        mov     ss, dx                                         ;#0074: 8E D2
        mov     sp, 800h                                       ;#0076: BC 00 08
        xor     ax, ax                                         ;#0079: 33 C0
        mov     ds, ax                                         ;#007B: 8E D8
        mov     es, ax                                         ;#007D: 8E C0
        lds     si, [INT_1E_VECTOR]                            ;#007F: C5 36 78 00
        mov     di, DPT                                        ;#0083: BF 22 05
        mov     cx, 0Bh                                        ;#0086: B9 0B 00
        rep     movsb                                          ;#0089: F3 A4
        push    cs                                             ;#008B: 0E
        pop     ds                                             ;#008C: 1F
        cmp     byte [INITIAL_LBA_SECTOR], 0                   ;#008D: 80 3E 24 00 00
        jnz     short INT_1E                                   ;#0092: 75 0A
        cmp     byte [INITIAL_LBA_SECTOR+2], 0                 ;#0094: 80 3E 26 00 00
        jnz     short INT_1E                                   ;#0099: 75 03
        jmp     near SHOW_ERROR_AND_REBOOT                     ;#009B: E9 A2 00

INT_1E:
        ; Install custom DPT, patch INT 1Eh vector, then read the boot LBA
        xor     ax, ax                                         ;#009E: 33 C0
        mov     [es:INT_1E_VECTOR+2], ax                       ;#00A0: 26 A3 7A 00
        mov     word [es:INT_1E_VECTOR], DPT                   ;#00A4: 26 C7 06 78 00 22 05
        mov     ax, [DPT_PATCH_LAST_SECTOR]                    ;#00AB: A1 28 00
        mov     [es:DPT_LAST_SECTOR], al                       ;#00AE: 26 A2 26 05
        mov     [es:DPT_HEAD_DELAY], ah                        ;#00B2: 26 88 26 2B 05
        sti                                                    ;#00B7: FB
        push    cs                                             ;#00B8: 0E
        pop     es                                             ;#00B9: 07
        mov     ah, 0                                          ;#00BA: B4 00
        mov     dh, 0                                          ;#00BC: B6 00
        mov     dl, [SISNE_DRIVE_NUMBER]                       ;#00BE: 8A 16 22 00
        ; INT 13h AH=0 — reset disk system; DL=drive, CF set on error
        int     13h                                            ;#00C2: CD 13
        jb      short SHOW_ERROR_AND_REBOOT                    ;#00C4: 72 7A
        push    cs                                             ;#00C6: 0E
        pop     ax                                             ;#00C7: 58
        sub     ax, 20h                                        ;#00C8: 2D 20 00
        mov     es, ax                                         ;#00CB: 8E C0
        mov     [FAR_LOADER_SEGMENT], ax                       ;#00CD: A3 97 01
        mov     word [FAR_LOADER_OFFSET], 0                    ;#00D0: C7 06 95 01 00 00
        mov     byte [SECTORS_REMAINING_SCRATCH], 1            ;#00D6: C6 06 2E 00 01
        mov     ax, [INITIAL_LBA_SECTOR]                       ;#00DB: A1 24 00
        mov     dx, [INITIAL_LBA_SECTOR+2]                     ;#00DE: 8B 16 26 00
        add     ax, [BPB_HIDDEN_SECTORS]                       ;#00E2: 03 06 1C 00
        adc     dx, [BPB_HIDDEN_SECTORS+2]                     ;#00E6: 13 16 1E 00
        call    near LBA_TO_CHS                                ;#00EA: E8 11 00
        push    es                                             ;#00ED: 06
        pop     ds                                             ;#00EE: 1F
        push    cs                                             ;#00EF: 0E
        pop     es                                             ;#00F0: 07
        mov     bx, LBA_TO_CHS_FAR                             ;#00F1: BB 7B 01
        push    cs                                             ;#00F4: 0E
        pop     ax                                             ;#00F5: 58
        mov     cx, MSG_INVALID_DISK                           ;#00F6: B9 99 01
        jmp     far word [es:FAR_LOADER_OFFSET]                ;#00F9: 26 FF 2E 95 01

LBA_TO_CHS:
        ; LBA→CHS: in dx:ax = LBA, out CL/CH/DH/DL set for INT 13h read
        div     word [BPB_SECTORS_PER_TRACK]                   ;#00FE: F7 36 18 00
        inc     dl                                             ;#0102: FE C2
        push    dx                                             ;#0104: 52
        xor     dx, dx                                         ;#0105: 33 D2
        div     word [BPB_HEAD_COUNT]                          ;#0107: F7 36 1A 00
        mov     [SISNE_HEAD_NUMBER], dl                        ;#010B: 88 16 23 00
        mov     dx, ax                                         ;#010F: 8B D0
        mov     cl, 6                                          ;#0111: B1 06
        shl     dh, cl                                         ;#0113: D2 E6
        pop     cx                                             ;#0115: 59
        or      dh, cl                                         ;#0116: 0A F1
        mov     cx, dx                                         ;#0118: 8B CA
        xchg    ch, cl                                         ;#011A: 86 CD
        mov     dx, [SISNE_DRIVE_NUMBER]                       ;#011C: 8B 16 22 00
        xor     bx, bx                                         ;#0120: 33 DB
READ_LOOP_TOP:
        ; Outer track-read loop: reset retry counter (BP=3)
        mov     bp, 3                                          ;#0122: BD 03 00
READ_TRY:
        ; Inner retry target: recompute sectors-this-track and try the read
        mov     al, [BPB_SECTORS_PER_TRACK]                    ;#0125: A0 18 00
        inc     al                                             ;#0128: FE C0
        sub     al, cl                                         ;#012A: 2A C1
        cmp     [SECTORS_REMAINING_SCRATCH], al                ;#012C: 38 06 2E 00
        jnb     short READ_USE_REMAINING                       ;#0130: 73 03
        mov     al, [SECTORS_REMAINING_SCRATCH]                ;#0132: A0 2E 00
READ_USE_REMAINING:
        ; Tail of last track — read only the remaining sectors
        ; (less than a full sectors-per-track; one INT 13h read can't cross a track)
        mov     ah, 2                                          ;#0135: B4 02
        push    ax                                             ;#0137: 50
        ; INT 13h AH=2 — read AL sectors from disk into ES:BX
        ; CH=cyl-lo, CL=sec|cyl-hi, DH=head, DL=drive
        int     13h                                            ;#0138: CD 13
        pop     ax                                             ;#013A: 58
        jnb     short READ_OK                                  ;#013B: 73 0F
        dec     bp                                             ;#013D: 4D
        jnz     short READ_TRY                                 ;#013E: 75 E5
SHOW_ERROR_AND_REBOOT:
        ; Print MSG_INVALID_DISK, wait for key (INT 16h), reboot (INT 19h)
        mov     si, MSG_INVALID_DISK                           ;#0140: BE 99 01
        call    near PRINT_LOOP                                ;#0143: E8 41 00
        mov     ah, 0                                          ;#0146: B4 00
        ; INT 16h AH=0 — wait for keystroke; returns AL=ASCII / AH=scancode
        int     16h                                            ;#0148: CD 16
        ; INT 19h — restart bootstrap (reload sector 0 to 0000:7C00); does not return
        int     19h                                            ;#014A: CD 19
READ_OK:
        ; One disk read succeeded — advance counters and continue
        push    dx                                             ;#014C: 52
        push    ax                                             ;#014D: 50
        cbw                                                    ;#014E: 98
        mul     word [BPB_BYTES_PER_SECTOR]                    ;#014F: F7 26 0B 00
        add     bx, ax                                         ;#0153: 03 D8
        pop     ax                                             ;#0155: 58
        pop     dx                                             ;#0156: 5A
        sub     [SECTORS_REMAINING_SCRATCH], al                ;#0157: 28 06 2E 00
        jbe     short SUBROUTINE_RET                           ;#015B: 76 1D
        add     cl, al                                         ;#015D: 02 C8
        cmp     cl, [BPB_SECTORS_PER_TRACK]                    ;#015F: 3A 0E 18 00
        jbe     short READ_LOOP_TOP                            ;#0163: 76 BD
        mov     cl, 1                                          ;#0165: B1 01
        inc     dh                                             ;#0167: FE C6
        cmp     dh, [BPB_HEAD_COUNT]                           ;#0169: 3A 36 1A 00
        jb      short READ_LOOP_TOP                            ;#016D: 72 B3
        xor     dh, dh                                         ;#016F: 32 F6
        inc     ch                                             ;#0171: FE C5
        jnz     short READ_LOOP_TOP                            ;#0173: 75 AD
        add     cl, 40h                                        ;#0175: 80 C1 40
        jmp     short READ_LOOP_TOP                            ;#0178: EB A8

SUBROUTINE_RET:
        ; Shared `ret` used by both LBA_TO_CHS and PRINT_LOOP
        ret                                                    ;#017A: C3

LBA_TO_CHS_FAR:
        ; Far entry: save CL → SECTORS_REMAINING_SCRATCH, DS=CS, call LBA_TO_CHS
        push    ds                                             ;#017B: 1E
        push    cs                                             ;#017C: 0E
        pop     ds                                             ;#017D: 1F
        mov     [SECTORS_REMAINING_SCRATCH], cl                ;#017E: 88 0E 2E 00
        call    near LBA_TO_CHS                                ;#0182: E8 79 FF
        pop     ds                                             ;#0185: 1F
        retf                                                   ;#0186: CB

PRINT_LOOP:
        ; lodsb, mask high bit, teletype via INT 10h, until terminator
        lodsb                                                  ;#0187: AC
        and     al, 7Fh                                        ;#0188: 24 7F
        jz      short SUBROUTINE_RET                           ;#018A: 74 EE
        mov     ah, 0Eh                                        ;#018C: B4 0E
        mov     bx, 7                                          ;#018E: BB 07 00
        ; INT 10h AH=0Eh — teletype output; AL=char, BH=page (0), BL=color (7)
        int     10h                                            ;#0191: CD 10
        jmp     short PRINT_LOOP                               ;#0193: EB F2

FAR_LOADER_OFFSET:
        ; Runtime-built far pointer — offset word (paired with SEGMENT at +2)
        dw      006Dh                                          ;#0195: 6D 00

FAR_LOADER_SEGMENT:
        ; Runtime-built far pointer — segment word (used by JMP FAR [..])
        dw      0                                              ;#0197: 00 00

MSG_INVALID_DISK:
        ; "Disco de sistema invalido ou defeituoso..."
        db      0Dh, 0Ah, ">>> "                               ;#0199: 0D 0A 3E 3E 3E 20
        db      "Disco de sistema invalido ou defeituoso. "    ;#019F: 44 69 73 63 6F 20 64 ...
        db      "Corrija e digite uma tecla"                   ;#01C8: 43 6F 72 72 69 6A 61 ...
        db      7                                              ;#01E2: 07
        times   27 db 0                                        ;#01E3: 00 00 00 00 00 00 00 ...
        db      55h, 0AAh                                      ;#01FE

END_POINTER:
        end
