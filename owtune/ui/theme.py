"""프로토타입(OW Tune.dc.html)의 어두운 테마를 Qt 스타일시트로 옮긴 것."""

BG = "#0E1013"
NAV = "#0B0D10"
PANEL = "#12151A"
PANEL2 = "#14171C"
HOVER = "#1B1F26"
LINE = "#1C2027"
LINE2 = "#252A32"
LINE3 = "#2F353F"
TEXT = "#E9ECEF"
SUB = "#A3ABB6"
MUTED = "#7F8894"
DIM = "#4A515C"
ACCENT = "#C6F36B"
ON_ACCENT = "#151A0A"
OK = "#6FD3C1"
WARN = "#F1B45A"

SANS = "'Segoe UI', 'Malgun Gothic'"
MONO = "'Cascadia Mono', 'Consolas', 'Malgun Gothic'"

# 근거 배지: (문구, 색, 테두리 모양, 설명)
BADGES = {
    "confirmed": ("유지 확인", OK, "solid", "이 PC에서 적용 뒤 게임이 다시 저장했을 때 값이 그대로 남은 키"),
    "seen": ("게임 기록 키", OK, "dashed", "게임이 이 PC 설정 파일에 직접 저장한 키. 값의 의미는 커뮤니티 근거"),
    "community": ("커뮤니티 근거", WARN, "dashed", "커뮤니티 게시물로만 알려진 키. 게임 실행 후 유지되는지 확인하세요"),
    "override": ("직접 지정", ACCENT, "solid", "상세 설정에서 직접 고른 값"),
    "manual": ("직접 선택", SUB, "solid", "환경·취향에 따라 달라서 자동으로 바꾸지 않는 옵션"),
    "display": ("Windows", SUB, "solid", "게임 파일이 아닌 Windows 디스플레이 설정"),
}

QSS = f"""
* {{ font-family: {SANS}; color: {TEXT}; }}
QMainWindow, #root {{ background: {BG}; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {LINE3}; padding: 6px; }}

#nav {{ background: {NAV}; border-right: 1px solid {LINE}; }}
#navBtn {{ text-align: left; padding: 0 12px; border: 0; border-radius: 5px;
          background: transparent; color: {SUB}; font-size: 13px; font-weight: 500; min-height: 38px; }}
#navBtn:hover {{ background: {HOVER}; }}
#navBtn:checked {{ background: {HOVER}; color: {TEXT}; }}
#navFoot {{ color: {MUTED}; font-size: 11px; border-top: 1px solid {LINE}; padding-top: 10px; }}

QLabel {{ background: transparent; }}
QLabel[role="h"] {{ font-size: 13px; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="sub"] {{ color: {SUB}; font-size: 12px; }}
QLabel[role="muted"] {{ color: {MUTED}; font-size: 11px; }}
QLabel[role="key"] {{ color: {MUTED}; font-family: {MONO}; font-size: 10px; letter-spacing: 1px; }}
QLabel[role="mono"] {{ font-family: {MONO}; font-size: 12px; }}
QLabel[role="value"] {{ font-size: 14px; font-weight: 600; }}

#strip {{ background: {LINE}; border: 1px solid {LINE}; border-radius: 6px; }}
#cell {{ background: {PANEL}; }}
#card {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 6px; }}
#cardHead {{ border-bottom: 1px solid {LINE}; }}
#cardFoot {{ background: {PANEL2}; border-top: 1px solid {LINE2};
             border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; }}
#bar {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 6px; }}
#row {{ border-bottom: 1px solid #181B21; }}
#warnStrip {{ background: #1F1A12; border: 1px solid #3A2F1C; border-radius: 4px; }}
#warnStrip QLabel {{ color: #D9CDB8; font-size: 12px; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {LINE3}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

/* 선택 버튼(목표 FPS·주사율) */
#pick {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 4px; color: {TEXT};
         font-family: {MONO}; font-size: 14px; font-weight: 600; min-height: 34px; }}
#pick:hover {{ border-color: {DIM}; }}
#pick:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: {ON_ACCENT}; }}
#pick:disabled {{ color: {DIM}; border-color: {LINE}; }}

/* 우선순위 카드 */
#prio {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 5px; text-align: left; }}
#prio:hover {{ border-color: {DIM}; }}
#prio:checked {{ background: #1B2112; border-color: {ACCENT}; }}

/* 세그먼트 */
#seg {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 5px; }}
#segBtn {{ background: transparent; border: 0; border-radius: 3px; color: {SUB};
           font-size: 12px; font-weight: 500; min-height: 28px; padding: 0 10px; }}
#segBtn:hover {{ color: {TEXT}; }}
#segBtn:checked {{ background: #252B33; color: {TEXT}; }}
#segBtn[accent="true"]:checked {{ background: {ACCENT}; color: {ON_ACCENT}; }}
#segBtn:disabled {{ color: {DIM}; }}
#seg[dots="true"] #segBtn {{ min-height: 32px; padding-bottom: 6px; }}

QLineEdit {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 4px; color: {TEXT};
             font-family: {MONO}; font-size: 13px; min-height: 34px; padding: 0 6px; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit[active="true"] {{ border-color: {ACCENT}; }}

#primary {{ background: {ACCENT}; color: {ON_ACCENT}; border: 0; border-radius: 5px;
            font-size: 14px; font-weight: 700; min-height: 42px; padding: 0 26px; }}
#primary:hover {{ background: #D4F68A; }}
#primary:disabled {{ background: {LINE2}; color: {MUTED}; }}
#ghost {{ background: transparent; color: {TEXT}; border: 1px solid {LINE3}; border-radius: 4px;
          font-size: 12px; min-height: 30px; padding: 0 12px; }}
#ghost:hover {{ border-color: {DIM}; }}
#ghost:disabled {{ color: {DIM}; border-color: {LINE}; }}
#link {{ background: transparent; border: 0; color: {SUB}; font-size: 12px; padding: 0; }}
#link:hover {{ color: {TEXT}; }}
#accentLink {{ background: transparent; border: 0; color: {ACCENT}; font-size: 12px; padding: 0; }}

#tab {{ background: transparent; border: 0; border-bottom: 2px solid transparent; color: {MUTED};
        font-size: 14px; font-weight: 600; min-height: 40px; padding: 0 16px; }}
#tab:checked {{ color: {TEXT}; border-bottom-color: {ACCENT}; }}
#tabBar {{ border-bottom: 1px solid {LINE}; }}

#monitor {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 5px; text-align: left; }}
#monitor:hover {{ border-color: {DIM}; }}
#monitor:checked {{ background: #151A10; border-color: {ACCENT}; }}
#monitor:disabled {{ background: {BG}; }}

QCheckBox {{ color: {SUB}; font-size: 12px; spacing: 8px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {DIM}; border-radius: 3px; background: transparent; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QDialog {{ background: {PANEL2}; border: 1px solid {LINE3}; }}
QProgressBar {{ background: {LINE2}; border: 0; border-radius: 2px; max-height: 3px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}

#toast {{ background: {TEXT}; color: {BG}; border-radius: 5px; padding: 10px 16px;
          font-size: 13px; font-weight: 500; }}
"""
