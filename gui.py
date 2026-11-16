import logging
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from classes import ALLOWED_TRANSITIONS, Cart, ShopError
from shop_service import change_order_status, place_order, sales_analytics
from storage import Storage

log = logging.getLogger(__name__)

BG = "#f4f5f9"
CARD = "#ffffff"
PRIMARY = "#4f46e5"
PRIMARY_DARK = "#4338ca"
TEXT = "#1f2937"
MUTED = "#9ca3af"
WARN = "#d97706"
DANGER = "#dc2626"
SUCCESS = "#16a34a"

TYPE_LABELS = {"physical": "Фізичний", "digital": "Цифровий"}
SEGMENT_LABELS = {"VIP": "VIP", "Regular": "Постійний", "Low-value": "Низька цінність"}


def money(value):
    value = float(value)
    text = f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"
    return text.replace(",", " ") + " грн"


class ShopApp(tk.Tk):
    SORTS = {
        "За популярністю": lambda p: -p.popularity,
        "Ціна: від дешевих": lambda p: p.base_price,
        "Ціна: від дорогих": lambda p: -p.base_price,
        "За назвою": lambda p: p.name.lower(),
    }

    def __init__(self):
        super().__init__()
        self.title("Інтернет-магазин")
        self.geometry("1100x720")
        self.minsize(960, 620)
        self.configure(bg=BG)

        self.storage = Storage()
        self.catalog = []
        self.cart = Cart()
        self._chart_data = ([], [])

        self._setup_style()
        self._build_header()

        self.status = tk.StringVar(value="Готово до роботи")
        self.status_label = tk.Label(self, textvariable=self.status, anchor="w", bg=BG,
                                     fg=MUTED, padx=18, pady=6)
        self.status_label.pack(side="bottom", fill="x")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=16, pady=(12, 0))

        self._build_catalog_tab()
        self._build_cart_tab()
        self._build_orders_tab()
        self._build_analytics_tab()


        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._reload_catalog()
        self.refresh_catalog()
        self.refresh_cart()

    def _setup_style(self):
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(size=10)
        tkfont.nametofont("TkTextFont").configure(size=10)
        self.font_bold = base.copy()
        self.font_bold.configure(weight="bold")
        self.font_big = base.copy()
        self.font_big.configure(size=20, weight="bold")

        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, fieldbackground=CARD)
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Card.TLabel", background=CARD)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("TCheckbutton", background=BG)
        s.configure("TLabelframe", background=BG, bordercolor="#d1d5db")
        s.configure("TLabelframe.Label", background=BG, foreground=TEXT, font=self.font_bold)

        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", padding=(20, 9), background="#e5e7eb", foreground=TEXT)
        s.map("TNotebook.Tab",
              background=[("selected", CARD)], foreground=[("selected", PRIMARY)])

        s.configure("Treeview", rowheight=30, background=CARD, fieldbackground=CARD,
                    bordercolor="#e5e7eb", borderwidth=1)
        s.configure("Treeview.Heading", background="#eef0f6", foreground=TEXT,
                    font=self.font_bold, padding=(6, 7), relief="flat")
        s.map("Treeview", background=[("selected", PRIMARY)],
              foreground=[("selected", "#ffffff")])

        s.configure("TButton", padding=(14, 7), background="#e5e7eb", borderwidth=0)
        s.map("TButton", background=[("active", "#d1d5db")])
        s.configure("Accent.TButton", background=PRIMARY, foreground="#ffffff",
                    font=self.font_bold, padding=(16, 9))
        s.map("Accent.TButton", background=[("active", PRIMARY_DARK), ("disabled", MUTED)])
        s.configure("Danger.TButton", foreground=DANGER)

    def _build_header(self):
        bar = tk.Frame(self, bg=PRIMARY)
        bar.pack(fill="x")
        tk.Label(bar, text="🛒  Інтернет-магазин", bg=PRIMARY, fg="white",
                 font=self.font_big, padx=20, pady=14).pack(side="left")
        self.header_cart = tk.Label(bar, text="", bg=PRIMARY, fg="white",
                                    font=self.font_bold, padx=20)
        self.header_cart.pack(side="right")

    def _set_status(self, text, color=MUTED):
        self.status.set(text)
        self.status_label.configure(fg=color)

    def _build_catalog_tab(self):
        tab = ttk.Frame(self.nb, padding=16)
        self.nb.add(tab, text="  Каталог  ")

        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 12))
        ttk.Label(bar, text="Пошук:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_catalog())
        ttk.Entry(bar, textvariable=self.search_var, width=28).pack(side="left", padx=(6, 18))

        ttk.Label(bar, text="Сортування:").pack(side="left")
        self.sort_var = tk.StringVar(value="За популярністю")
        cb = ttk.Combobox(bar, textvariable=self.sort_var, values=list(self.SORTS),
                          state="readonly", width=20)
        cb.pack(side="left", padx=(6, 18))
        cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh_catalog())

        self.in_stock_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Лише в наявності", variable=self.in_stock_var,
                        command=self.refresh_catalog).pack(side="left")

        cols = ("id", "name", "type", "price", "ship", "stock", "pop")
        self.cat_tree = ttk.Treeview(tab, columns=cols, show="headings", selectmode="browse")
        for col, title, w, anchor in [
            ("id", "ID", 50, "center"), ("name", "Назва", 260, "w"),
            ("type", "Тип", 100, "center"), ("price", "Ціна", 120, "e"),
            ("ship", "Доставка", 100, "e"),
            ("stock", "В наявності", 100, "center"), ("pop", "Популярність", 100, "center"),
        ]:
            self.cat_tree.heading(col, text=title)
            self.cat_tree.column(col, width=w, anchor=anchor)
        self.cat_tree.tag_configure("out", foreground=MUTED)
        self.cat_tree.tag_configure("low", foreground=WARN)
        self.cat_tree.pack(fill="both", expand=True)
        self.cat_tree.bind("<Double-1>", self._on_catalog_double_click)

        bottom = ttk.Frame(tab)
        bottom.pack(fill="x", pady=(12, 0))
        ttk.Label(bottom, text="Кількість:").pack(side="left")
        self.qty_var = tk.StringVar(value="1")
        ttk.Spinbox(bottom, from_=1, to=99, width=5, textvariable=self.qty_var).pack(
            side="left", padx=(6, 14))
        ttk.Button(bottom, text="➕  Додати в кошик", style="Accent.TButton",
                   command=self.add_selected).pack(side="left")
        ttk.Label(bottom, text="Подвійний клік по товару теж додає його в кошик",
                  style="Muted.TLabel").pack(side="right")

    def _reload_catalog(self):
        try:
            self.catalog = self.storage.load_catalog()
        except ShopError as exc:
            messagebox.showerror("Каталог", str(exc))

    def refresh_catalog(self):
        query = self.search_var.get().strip().lower()
        items = [p for p in self.catalog
                 if (not query or query in p.name.lower() or query == str(p.product_id))
                 and (not self.in_stock_var.get() or p.stock > 0)]
        items.sort(key=self.SORTS[self.sort_var.get()])

        self.cat_tree.delete(*self.cat_tree.get_children())
        for p in items:
            tag = "out" if p.stock <= 0 else ("low" if p.stock <= 3 else "")
            shipping = money(p.shipping_cost()) if p.shipping_cost() else "—"
            self.cat_tree.insert("", "end", iid=str(p.product_id), tags=(tag,), values=(
                p.product_id, p.name, TYPE_LABELS.get(p.product_type, p.product_type),
                money(p.base_price), shipping, p.stock if p.stock > 0 else "немає", p.popularity))

    def _on_catalog_double_click(self, event):
        row = self.cat_tree.identify_row(event.y)
        if row:
            self.cat_tree.selection_set(row)
            self.add_selected()

    def find_product(self, product_id):
        return next((p for p in self.catalog if p.product_id == product_id), None)

    def add_selected(self):
        sel = self.cat_tree.selection()
        if not sel:
            messagebox.showinfo("Каталог", "Спочатку виберіть товар у списку.")
            return
        product = self.find_product(int(sel[0]))
        try:
            qty = int(self.qty_var.get())
        except ValueError:
            messagebox.showwarning("Кількість", "Введіть кількість цілим числом.")
            return
        try:
            self.cart.add(product, qty)
        except ShopError as exc:
            messagebox.showwarning("Не вдалося додати в кошик", str(exc))
            return
        self.refresh_cart()
        self._set_status(f"✓ «{product.name}» × {qty} додано в кошик", SUCCESS)

    def _build_cart_tab(self):
        self.cart_tab = ttk.Frame(self.nb, padding=16)
        self.nb.add(self.cart_tab, text="  Кошик  ")

        left = ttk.Frame(self.cart_tab)
        left.pack(side="left", fill="both", expand=True)

        cols = ("name", "price", "qty", "sum")
        self.cart_tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for col, title, w, anchor in [
            ("name", "Товар", 240, "w"), ("price", "Ціна з доставкою", 150, "e"),
            ("qty", "К-сть", 70, "center"), ("sum", "Сума", 130, "e"),
        ]:
            self.cart_tree.heading(col, text=title)
            self.cart_tree.column(col, width=w, anchor=anchor)
        self.cart_tree.pack(fill="both", expand=True)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(12, 0))
        ttk.Button(btns, text="−", width=3, command=lambda: self.change_qty(-1)).pack(side="left")
        ttk.Button(btns, text="+", width=3, command=lambda: self.change_qty(1)).pack(
            side="left", padx=6)
        ttk.Button(btns, text="Видалити", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(btns, text="Очистити кошик", style="Danger.TButton",
                   command=self.clear_cart).pack(side="left")

        # права панель — оформлення замовлення
        right = ttk.Frame(self.cart_tab, style="Card.TFrame", padding=20)
        right.pack(side="right", fill="y", padx=(16, 0))
        ttk.Label(right, text="Оформлення замовлення", style="Card.TLabel",
                  font=self.font_bold).pack(anchor="w", pady=(0, 14))

        ttk.Label(right, text="Ім'я", style="Card.TLabel").pack(anchor="w")
        self.name_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.name_var, width=30).pack(fill="x", pady=(2, 10))
        ttk.Label(right, text="Email", style="Card.TLabel").pack(anchor="w")
        self.email_var = tk.StringVar()
        ttk.Entry(right, textvariable=self.email_var, width=30).pack(fill="x", pady=(2, 18))

        ttk.Separator(right).pack(fill="x", pady=(0, 12))
        ttk.Label(right, text="Разом до сплати", style="Card.TLabel").pack(anchor="w")
        self.total_label = tk.Label(right, text="0 грн", bg=CARD, fg=PRIMARY, font=self.font_big)
        self.total_label.pack(anchor="w", pady=(0, 16))
        ttk.Button(right, text="Оформити замовлення", style="Accent.TButton",
                   command=self.checkout).pack(fill="x")

    def refresh_cart(self):
        self.cart_tree.delete(*self.cart_tree.get_children())
        for product, qty in self.cart.lines():
            unit = product.calculate_total_price()
            self.cart_tree.insert("", "end", iid=str(product.product_id), values=(
                product.name, money(unit), qty, money(unit * qty)))

        count, total = self.cart.count, self.cart.total
        self.total_label.configure(text=money(total))
        self.nb.tab(self.cart_tab, text=f"  Кошик ({count})  " if count else "  Кошик  ")
        self.header_cart.configure(
            text=f"Кошик: {count} шт. · {money(total)}" if count else "Кошик порожній")

    def _selected_cart_product(self):
        sel = self.cart_tree.selection()
        if not sel:
            messagebox.showinfo("Кошик", "Виберіть товар у кошику.")
            return None
        pid = int(sel[0])
        return next((p for p, _ in self.cart.lines() if p.product_id == pid), None)

    def change_qty(self, delta):
        product = self._selected_cart_product()
        if product is None:
            return
        new_qty = self.cart.quantity_of(product.product_id) + delta
        try:
            self.cart.set_quantity(product, max(0, new_qty))
        except ShopError as exc:
            messagebox.showwarning("Кількість", str(exc))
            return
        self.refresh_cart()
        if self.cart.quantity_of(product.product_id):
            self.cart_tree.selection_set(str(product.product_id))

    def remove_selected(self):
        product = self._selected_cart_product()
        if product is not None:
            self.cart.remove(product.product_id)
            self.refresh_cart()

    def clear_cart(self):
        if not self.cart.is_empty and messagebox.askyesno("Кошик", "Очистити весь кошик?"):
            self.cart.clear()
            self.refresh_cart()

    def checkout(self):
        try:
            order = place_order(self.storage, self.cart,
                                self.name_var.get(), self.email_var.get())
        except ShopError as exc:
            messagebox.showerror("Не вдалося оформити замовлення", str(exc))
            self._reload_catalog()  # залишки могли змінитись — оновлюємо каталог
            self.refresh_catalog()
            return

        self.name_var.set("")
        self.email_var.set("")
        self._reload_catalog()
        self.refresh_catalog()
        self.refresh_cart()
        self._set_status(f"✓ Замовлення #{order.order_id} збережено", SUCCESS)
        messagebox.showinfo("Дякуємо за замовлення!",
                            f"Замовлення #{order.order_id} оформлено.\nДо сплати: {money(order.total)}")

    def _build_orders_tab(self):
        tab = ttk.Frame(self.nb, padding=16)
        self.nb.add(tab, text="  Замовлення  ")

        left = ttk.Frame(tab)
        left.pack(side="left", fill="both", expand=True)
        cols = ("id", "customer", "date", "status", "total")
        self.orders_tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for col, title, w, anchor in [
            ("id", "№", 45, "center"), ("customer", "Клієнт", 140, "w"),
            ("date", "Дата", 90, "center"), ("status", "Статус", 100, "center"),
            ("total", "Сума", 110, "e"),
        ]:
            self.orders_tree.heading(col, text=title)
            self.orders_tree.column(col, width=w, anchor=anchor)
        self.orders_tree.tag_configure("Cancelled", foreground=MUTED)
        self.orders_tree.pack(fill="both", expand=True)
        self.orders_tree.bind("<<TreeviewSelect>>", self._show_order_details)
        ttk.Button(left, text="⟳  Оновити", command=self.refresh_orders).pack(
            anchor="w", pady=(12, 0))

        right = ttk.Frame(tab, style="Card.TFrame", padding=20)
        right.pack(side="right", fill="both", expand=True, padx=(16, 0))
        self.order_title = ttk.Label(right, text="Виберіть замовлення зі списку",
                                     style="Card.TLabel", font=self.font_bold)
        self.order_title.pack(anchor="w")
        self.order_info = ttk.Label(right, text="", style="Card.TLabel")
        self.order_info.pack(anchor="w", pady=(4, 12))

        self.order_items = ttk.Treeview(right, columns=("name", "price", "qty", "sum"),
                                        show="headings", height=8)
        for col, title, w, anchor in [
            ("name", "Товар", 150, "w"), ("price", "Ціна", 95, "e"),
            ("qty", "К-сть", 55, "center"), ("sum", "Сума з доставкою", 150, "e"),
        ]:
            self.order_items.heading(col, text=title)
            self.order_items.column(col, width=w, anchor=anchor)
        self.order_items.pack(fill="both", expand=True)
        self.order_total = tk.Label(right, text="", bg=CARD, fg=PRIMARY, font=self.font_bold)
        self.order_total.pack(anchor="e", pady=(10, 0))

        status_row = ttk.Frame(right, style="Card.TFrame")
        status_row.pack(fill="x", pady=(14, 0))
        ttk.Label(status_row, text="Змінити статус на:", style="Card.TLabel").pack(side="left")
        self.status_var = tk.StringVar()
        self.status_combo = ttk.Combobox(status_row, textvariable=self.status_var,
                                         state="disabled", width=16)
        self.status_combo.pack(side="left", padx=8)
        self.status_btn = ttk.Button(status_row, text="Застосувати", style="Accent.TButton",
                                     command=self.apply_status, state="disabled")
        self.status_btn.pack(side="left")

        self._orders_by_id = {}

    def refresh_orders(self, select=None):
        self._orders_by_id = {o.order_id: o for o in self.storage.iter_orders()}
        self.orders_tree.delete(*self.orders_tree.get_children())
        for order in reversed(list(self._orders_by_id.values())):  # нові зверху
            self.orders_tree.insert("", "end", iid=str(order.order_id),
                                    tags=(order.status.value,), values=(
                order.order_id, order.customer.name, order.created, order.status.label,
                money(order.total)))
        self._clear_order_details()
        if select in self._orders_by_id:
            self.orders_tree.selection_set(str(select))

    def _clear_order_details(self):
        self.order_title.configure(text="Виберіть замовлення зі списку")
        self.order_info.configure(text="")
        self.order_items.delete(*self.order_items.get_children())
        self.order_total.configure(text="")
        self.status_var.set("")
        self.status_combo.configure(state="disabled", values=())
        self.status_btn.configure(state="disabled")

    def _selected_order(self):
        sel = self.orders_tree.selection()
        return self._orders_by_id.get(int(sel[0])) if sel else None

    def _show_order_details(self, _event=None):
        order = self._selected_order()
        if order is None:
            return
        self.order_title.configure(text=f"Замовлення #{order.order_id}")
        self.order_info.configure(text=(
            f"{order.customer.name}  ·  {order.customer.email}  ·  {order.created}  ·  "
            f"{order.status.label}"))
        self.order_items.delete(*self.order_items.get_children())
        for item in order.items:
            self.order_items.insert("", "end", values=(
                item.title, money(item.unit_price), item.quantity, money(item.total)))
        self.order_total.configure(text=(
            f"Товари: {money(order.goods_total)}  ·  Доставка: {money(order.shipping_total)}  ·  "
            f"Разом: {money(order.total)}"))

        options = ALLOWED_TRANSITIONS[order.status]
        self.status_var.set("")
        if options:
            self.status_combo.configure(state="readonly", values=[s.label for s in options])
            self.status_btn.configure(state="normal")
        else:
            self.status_combo.configure(state="disabled", values=())
            self.status_btn.configure(state="disabled")

    def apply_status(self):
        order = self._selected_order()
        if order is None:
            return
        chosen = next((s for s in ALLOWED_TRANSITIONS[order.status]
                       if s.label == self.status_var.get()), None)
        if chosen is None:
            messagebox.showinfo("Статус", "Виберіть новий статус зі списку.")
            return
        try:
            change_order_status(self.storage, order.order_id, chosen)
        except ShopError as exc:
            messagebox.showerror("Не вдалося змінити статус", str(exc))
            return
        self._reload_catalog()  # скасування повертає товари на склад
        self.refresh_catalog()
        self.refresh_orders(select=order.order_id)
        self._set_status(f"✓ Замовлення #{order.order_id}: статус «{chosen.label}»", SUCCESS)

    def _build_analytics_tab(self):
        tab = ttk.Frame(self.nb, padding=16)
        self.nb.add(tab, text="  Аналітика  ")

        cards = ttk.Frame(tab)
        cards.pack(fill="x", pady=(0, 14))
        self.stat_labels = {}
        for key, title in [("orders", "Замовлень"), ("revenue", "Виручка"),
                           ("avg", "Середній чек"), ("customers", "Клієнтів")]:
            card = ttk.Frame(cards, style="Card.TFrame", padding=(18, 12))
            card.pack(side="left", fill="x", expand=True, padx=(0, 12))
            ttk.Label(card, text=title, style="Card.TLabel", foreground=MUTED).pack(anchor="w")
            lbl = tk.Label(card, text="—", bg=CARD, fg=PRIMARY, font=self.font_big)
            lbl.pack(anchor="w")
            self.stat_labels[key] = lbl

        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1, uniform="a")
        body.columnconfigure(1, weight=1, uniform="a")
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        top_box = ttk.LabelFrame(body, text="Топ найприбутковіших товарів", padding=8)
        top_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.top_tree = self._small_tree(top_box, [
            ("name", "Товар", 170, "w"), ("sold", "Продано", 70, "center"),
            ("rev", "Виручка", 110, "e")])

        seg_box = ttk.LabelFrame(body, text="Сегментація клієнтів", padding=8)
        seg_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.seg_tree = self._small_tree(seg_box, [
            ("name", "Клієнт", 150, "w"), ("spent", "Витрачено", 100, "e"),
            ("seg", "Сегмент", 110, "center")])
        self.seg_tree.tag_configure("VIP", foreground=PRIMARY)
        self.seg_tree.tag_configure("Low-value", foreground=MUTED)

        dyn_box = ttk.LabelFrame(body, text="Динаміка виручки за днями", padding=8)
        dyn_box.grid(row=0, column=1, rowspan=2, sticky="nsew")
        self.chart = tk.Canvas(dyn_box, bg=CARD, height=180, highlightthickness=0)
        self.chart.pack(fill="x", pady=(0, 8))
        self.chart.bind("<Configure>", lambda _e: self._draw_chart())
        self.dyn_tree = self._small_tree(dyn_box, [
            ("date", "Дата", 90, "center"), ("rev", "Виручка", 100, "e"),
            ("cnt", "Замовлень", 80, "center"), ("avg", "Середній чек", 100, "e")])

    def _small_tree(self, parent, columns):
        tree = ttk.Treeview(parent, columns=[c[0] for c in columns], show="headings",
                            height=5)
        for col, title, w, anchor in columns:
            tree.heading(col, text=title)
            tree.column(col, width=w, anchor=anchor)
        tree.pack(fill="both", expand=True)
        return tree

    def refresh_analytics(self):
        for tree in (self.top_tree, self.seg_tree, self.dyn_tree):
            tree.delete(*tree.get_children())
        try:
            analytics = sales_analytics(self.storage)  # скасовані замовлення не враховуються
            df = analytics.df
        except Exception as exc:  # аналітика (pandas) не повинна «вбивати» вікно
            log.exception("Помилка аналітики")
            messagebox.showerror("Аналітика", f"Не вдалося обчислити аналітику:\n{exc}")
            return

        if df.empty:
            for lbl in self.stat_labels.values():
                lbl.configure(text="—")
            self._chart_data = ([], [])
            self._draw_chart()
            return

        revenue = float(df["total_revenue"].sum())
        n_orders = df["order_id"].nunique()
        self.stat_labels["orders"].configure(text=str(n_orders))
        self.stat_labels["revenue"].configure(text=money(revenue))
        self.stat_labels["avg"].configure(text=money(revenue / n_orders))
        self.stat_labels["customers"].configure(text=str(df["customer_name"].nunique()))

        for _, r in analytics.get_top_profitable_products().iterrows():
            self.top_tree.insert("", "end", values=(
                r["product_name"], int(r["total_sold"]), money(r["total_revenue"])))

        for _, r in analytics.segment_customers().iterrows():
            self.seg_tree.insert("", "end", tags=(r["segment"],), values=(
                r["customer_name"], money(r["total_spent"]),
                SEGMENT_LABELS.get(r["segment"], r["segment"])))

        dyn = analytics.get_revenue_dynamics()
        dyn = dyn[dyn["order_count"] > 0]
        for _, r in dyn.iloc[::-1].iterrows():
            self.dyn_tree.insert("", "end", values=(
                r["order_date"].strftime("%d.%m.%Y"), money(r["daily_revenue"]),
                int(r["order_count"]), money(r["avg_order_value"])))
        tail = dyn.tail(10)
        self._chart_data = ([d.strftime("%d.%m") for d in tail["order_date"]],
                            [float(v) for v in tail["daily_revenue"]])
        self._draw_chart()

    def _draw_chart(self):
        c = self.chart
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        labels, values = self._chart_data
        if w < 50:
            return
        if not values:
            c.create_text(w / 2, h / 2, text="Немає даних для аналізу", fill=MUTED)
            return
        pad_t, pad_b, pad_x = 24, 26, 12
        peak = max(values) or 1
        slot = (w - 2 * pad_x) / len(values)
        bar_w = min(56, slot * 0.6)
        for i, (lab, val) in enumerate(zip(labels, values)):
            x0 = pad_x + i * slot + (slot - bar_w) / 2
            bar_h = (h - pad_t - pad_b) * val / peak
            y0 = h - pad_b - bar_h
            c.create_rectangle(x0, y0, x0 + bar_w, h - pad_b, fill=PRIMARY, outline="")
            c.create_text(x0 + bar_w / 2, y0 - 9, text=f"{val:,.0f}".replace(",", " "),
                          fill=TEXT, font=("TkDefaultFont", 8))
            c.create_text(x0 + bar_w / 2, h - pad_b + 12, text=lab, fill=MUTED,
                          font=("TkDefaultFont", 8))

    def _on_tab_changed(self, _event=None):
        title = self.nb.tab(self.nb.select(), "text").strip()
        if title == "Замовлення":
            self.refresh_orders()
        elif title == "Аналітика":
            self.refresh_analytics()


if __name__ == "__main__":
    ShopApp().mainloop()
