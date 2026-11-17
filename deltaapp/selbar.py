"""Seçim çubuğu: tahtada bir şey seçilince üstünde beliren küçük çubuk (Canva'daki gibi).
Hizala / dağıt, diz (yan yana, alt alta, ızgara, çember), grupla, katman sırası, kilitle, sil.
Menülerin içeriğini Board kurar; aynı menüler sağ tık menüsünde de kullanılır."""
from PyQt6.QtCore import Qt, QRectF, QPoint, QRect
from PyQt6.QtGui import QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QMenu

from .i18n import t
from .theme import qcolor
from .widgets import IconButton


class SelectionBar(QWidget):
    GAP = 12   # seçimle çubuk arası (ekran pikseli)

    def __init__(self, board):
        super().__init__(board)
        self.board = board
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(1)

        def btn(name, tip, fn):
            b = IconButton(name, tip, 34, 20, parent=self)
            b.clicked.connect(fn)
            lay.addWidget(b)
            return b
        self.b_align = btn("align_left", t("sb_align"), lambda: self._menu(self.b_align, board.build_align_menu))
        self.b_arrange = btn("lay_grid", t("sb_arrange"), lambda: self._menu(self.b_arrange, board.build_arrange_menu))
        # bağlama göre: görsel → kırp, şekil → dolgu, yazı → biçim
        self.b_crop = btn("crop", t("sb_crop"), lambda: board.start_crop())
        self.b_fill = btn("fill", t("sb_fill"), lambda: self._menu(self.b_fill, board.build_fill_menu))
        self.b_bold = btn("format_bold", t("txt_bold"), lambda: board.toggle_text("bold"))
        self.b_italic = btn("format_italic", t("txt_italic"), lambda: board.toggle_text("italic"))
        self.b_under = btn("format_underlined", t("txt_underline"), lambda: board.toggle_text("underline"))
        for b in (self.b_bold, self.b_italic, self.b_under):
            b.setCheckable(True)
        self.b_bigger = btn("text_bigger", t("txt_bigger"), lambda: board.text_size(1.2))
        self.b_smaller = btn("text_smaller", t("txt_smaller"), lambda: board.text_size(1 / 1.2))
        self.b_talign = btn("talign_left", t("txt_align"), lambda: self._menu(self.b_talign, board.build_text_align_menu))
        self.b_table = btn("table", t("table"), self._table_menu)
        self.b_corner = btn("border_off", t("tbl_borderless"), self._corner_clicked)
        self.b_rotate = btn("rotate_right", t("sb_rotate"), lambda: self._menu(self.b_rotate, board.build_rotate_menu))
        self.b_opacity = btn("opacity", t("sb_opacity"), lambda: self._menu(self.b_opacity, board.build_opacity_menu))
        self.b_group = btn("group", t("sb_group"), self._group_clicked)
        self.b_layer = btn("layers", t("sb_layer"), lambda: self._menu(self.b_layer, board.build_layer_menu))
        self.b_lock = btn("lock", t("sb_lock"), board.lock_selection)
        self.b_delete = btn("delete", t("sb_delete"), board.delete_selection)
        self._ungroup = False
        self.hide()

    def _menu(self, b, build):
        m = QMenu(self)
        build(m)
        m.exec(b.mapToGlobal(QPoint(0, b.height() + 4)))

    def _table_menu(self):
        tb = self.board._sel_table()
        if tb is not None:
            self._menu(self.b_table, lambda m: self.board.build_table_menu(m, tb))

    def _corner_clicked(self):
        tb = self.board._sel_table()
        if tb is not None:
            self.board.set_table_border(tb, not tb.border)

    def _group_clicked(self):
        if self._ungroup:
            self.board.ungroup_selection()
        else:
            self.board.group_selection()

    def refresh(self, info):
        """info: Board.selection_info() → {"units", "items", "grouped", "can_group"}."""
        units = info["units"]
        self.b_align.setVisible(units >= 2)
        self.b_arrange.setVisible(units >= 2)
        self.b_crop.setVisible(info.get("images", 0) == 1 and info["items"] == 1)
        self.b_fill.setVisible(info.get("shapes", 0) > 0)
        tx = info.get("texts", 0) > 0
        tbl = info.get("tables", 0) > 0
        for b in (self.b_bold, self.b_italic, self.b_under, self.b_talign):
            b.setVisible(tx)
        for b in (self.b_bigger, self.b_smaller):
            b.setVisible(tx or tbl)
        one_table = info.get("tables", 0) == 1 and info["items"] == 1
        self.b_table.setVisible(one_table)
        self.b_corner.setVisible(one_table)
        # düğme, tıklayınca olacak köşeyi gösterir
        self.b_corner.set_icon_name("border_off" if info.get("border") else "border_on")
        self.b_corner.setToolTip(t("tbl_borderless") if info.get("border") else t("tbl_border"))
        for b, k in ((self.b_bold, "bold"), (self.b_italic, "italic"), (self.b_under, "underline")):
            b.setChecked(bool(info.get(k)))
        self._ungroup = info["grouped"] and not info["can_group"]
        self.b_group.set_icon_name("ungroup" if self._ungroup else "group")
        self.b_group.setToolTip(t("sb_ungroup") if self._ungroup else t("sb_group"))
        self.b_group.setEnabled(info["can_group"] or info["grouped"])
        self.adjustSize()

    def place(self, rect: QRectF):
        """rect: seçimin görünüm (viewport) koordinatındaki kutusu."""
        par = self.board
        self.adjustSize()
        w, h = self.width(), self.height()
        vp = par.viewport().geometry()
        x = int(rect.center().x() - w / 2) + vp.x()
        x = max(vp.x() + 6, min(x, vp.right() - w - 6))
        # araç çubuğu gibi üstüne binilmemesi gereken pencereler (Board.avoid)
        avoid = []
        for wd in getattr(par, "avoid", []):
            if wd is not None and wd.isVisible():
                avoid.append(QRect(par.mapFromGlobal(wd.mapToGlobal(QPoint(0, 0))), wd.size()).adjusted(-4, -4, 4, 4))
        gap = self.GAP + (30 if par._rot_handle() is not None else 0)   # döndürme tutamacına binmesin
        cands = (int(rect.top()) - h - gap + vp.y(),               # seçimin üstü
                 int(rect.bottom()) + self.GAP + vp.y(),           # altı
                 int(rect.top()) + self.GAP + vp.y())              # içinde, üst kenarda
        y = None
        for cy in cands:
            r = QRect(x, cy, w, h)
            if cy >= vp.y() + 6 and cy + h <= vp.bottom() - 6 and not any(r.intersects(a) for a in avoid):
                y = cy
                break
        if y is None:
            y = max(vp.y() + 6, min(cands[2], vp.bottom() - h - 6))
        self.move(x, y)
        self.show()
        self.raise_()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        rad = r.height() / 2
        path.addRoundedRect(r, rad, rad)
        p.fillPath(path, qcolor("dock"))
        p.setPen(QPen(qcolor("divider"), 1))
        p.drawPath(path)
