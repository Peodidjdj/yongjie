# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import json
import os # <-- 确保导入 os
import uuid
import time
import re

# 初始化应用
app = Flask(__name__)

# --- !! 修改 SECRET_KEY !! ---
# 从环境变量读取，提供一个本地备用值（这个备用值不应太简单）
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-complex-and-random-fallback-key-for-local-dev')

# --- !! 修改数据库路径指向 data 子目录 !! ---
basedir = os.path.abspath(os.path.dirname(__file__))
data_dir = os.path.join(basedir, 'data')
os.makedirs(data_dir, exist_ok=True) # 确保 data 目录存在
db_path = os.path.join(data_dir, 'restaurant.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
# --- !! 数据库路径修改结束 !! ---

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# 初始化数据库和登录管理器 (不变)
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录以访问此页面'
login_manager.login_message_category = 'info'

# --- 自定义 Jinja2 过滤器 (不变) ---
@app.template_filter('fromjson')
def from_json_filter(json_string):
    if json_string:
        try: return json.loads(json_string)
        except: return {}
    return {}

# --- 装饰器 (不变) ---
def role_required(roles):
    # ... (代码不变)
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                 flash('请先登录以访问此页面', 'info'); return redirect(url_for('login', next=request.url))
            if current_user.role not in roles:
                flash('您没有权限访问此页面', 'danger'); return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def rate_limit(max_calls=10, period=60):
    # ... (代码不变)
    _ip_records = {}
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr; current_time = time.time()
            if ip not in _ip_records: _ip_records[ip] = []
            _ip_records[ip] = [t for t in _ip_records[ip] if current_time - t < period]
            if len(_ip_records[ip]) >= max_calls: return jsonify({'error': '请求过于频繁，请稍后再试'}), 429
            _ip_records[ip].append(current_time)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# --- 数据库模型 (不变) ---
# ... (User, Dish, Order, OrderItem, Member, Ingredient, Supplier, PurchaseOrder, IngredientOption, Feedback, SmsMessage 模型定义) ...
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=True, index=True)
    role = db.Column(db.String(20), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def __repr__(self): return f'<User {self.username}>'

class Dish(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(255), nullable=True)
    ingredients = db.Column(db.Text, nullable=True)
    heritage_history = db.Column(db.Text, nullable=True)
    is_available = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    def __repr__(self): return f'<Dish {self.name}>'

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id', ondelete='SET NULL'), nullable=True, index=True)
    waiter_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    total_amount = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    final_amount = db.Column(db.Float, default=0.0)
    payment_method = db.Column(db.String(20), default='cash')
    status = db.Column(db.String(20), default='pending', index=True)
    is_online = db.Column(db.Boolean, default=False)
    source = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    member = db.relationship('Member', backref='orders')
    waiter = db.relationship('User', backref='served_orders')
    def __repr__(self): return f'<Order {self.order_number}>'

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id', ondelete='CASCADE'), nullable=False, index=True)
    dish_id = db.Column(db.Integer, db.ForeignKey('dish.id', ondelete='RESTRICT'), nullable=False, index=True)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, nullable=False)
    special_request = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order = db.relationship('Order', backref=db.backref('items', cascade="all, delete-orphan"))
    dish = db.relationship('Dish', backref=db.backref('order_items', lazy='joined'))
    def __repr__(self): return f'<OrderItem {self.quantity}x DishID:{self.dish_id} in OrderID:{self.order_id}>'

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), nullable=True, index=True)
    points = db.Column(db.Integer, default=0)
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_visit = db.Column(db.DateTime, default=datetime.utcnow)
    def is_anniversary(self):
        today = datetime.utcnow().date(); join_d = self.join_date.date()
        return today.day == join_d.day and today.month == join_d.month
    def __repr__(self): return f'<Member {self.name} ({self.phone})>'

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    unit = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Float, default=0.0)
    min_quantity = db.Column(db.Float, default=10.0)
    price_per_unit = db.Column(db.Float, nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def is_low_stock(self): return self.quantity <= self.min_quantity
    def __repr__(self): return f'<Ingredient {self.name}>'

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    contact_person = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    rating = db.Column(db.Float, default=5.0)
    status = db.Column(db.String(20), default='active')
    def __repr__(self): return f'<Supplier {self.name}>'

class PurchaseOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(20), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id', ondelete='RESTRICT'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    total_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    items = db.Column(db.Text) # JSON
    inspection_result = db.Column(db.Text) # JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    supplier = db.relationship('Supplier', backref='purchase_orders')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_pos')
    approver = db.relationship('User', foreign_keys=[approver_id], backref='approved_pos')
    def __repr__(self): return f'<PurchaseOrder {self.po_number}>'

class IngredientOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(50), index=True)
    price = db.Column(db.Float, default=0.0)
    is_available = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    incompatible_with = db.Column(db.Text, default='[]')
    def __repr__(self): return f'<IngredientOption {self.name} ({self.category})>'

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id', ondelete='SET NULL'), nullable=True, index=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id', ondelete='SET NULL'), nullable=True, index=True)
    rating = db.Column(db.Integer, default=5)
    comments = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending', index=True)
    order = db.relationship('Order', backref=db.backref('feedback', uselist=False))
    member = db.relationship('Member', backref='feedbacks')
    def __repr__(self): return f'<Feedback Rating:{self.rating} OrderID:{self.order_id}>'

class SmsMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='sent')
    def __repr__(self): return f'<SmsMessage To:{self.recipient} Status:{self.status}>'


# --- 用户加载与短信 (不变) ---
@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

def send_sms(phone, message): # ... (不变)
    if not phone: print(f"SMS发送失败: 接收人手机号为空。消息: {message}"); return False
    try:
        with app.app_context(): sms = SmsMessage(recipient=phone, content=message); db.session.add(sms); db.session.commit()
        print(f"[SMS模拟发送] 接收人: {phone}, 内容: {message}")
        return True
    except Exception as e: print(f"SMS发送失败: {str(e)}"); return False

def send_member_welcome(phone, name): return send_sms(phone, f"尊敬的{name}，欢迎成为永杰饭庄会员！积分满100可享6折优惠。")
def send_order_notification(phone, name, order_number, status): # ... (不变)
    status_map = {'pending': '已接收','cooking': '制作中','completed': '已完成','cancelled': '已取消'}
    return send_sms(phone, f"尊敬的{name}，您的订单 #{order_number} {status_map.get(status, '状态已更新')}。")
def send_low_stock_alert(phone, ingredient_name, quantity): return send_sms(phone, f"【库存预警】{ingredient_name}({quantity})低于阈值，请补充。")


# --- 路由 (大部分不变) ---
@app.route('/')
def home(): return redirect(url_for('customer_index'))

@app.route('/customer')
def customer_index():
    # ... (保持查询数据库的版本，不变) ...
    os.makedirs('templates/customer', exist_ok=True)
    tmpl = os.path.join('templates', 'customer', 'index.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    regular_dishes = []
    try:
        print("DEBUG [customer_index]: Querying DB: category ilike 'regular', is_available == 1")
        regular_dishes = Dish.query.filter(
            Dish.category.ilike('regular'),
            Dish.is_available == 1 # Or == True
        ).order_by(Dish.name).all()
        print(f"DEBUG [customer_index]: Found {len(regular_dishes)} dishes.")
    except Exception as e:
        print(f"ERROR [customer_index] querying regular dishes: {e}")
        flash("加载菜单时出错，请稍后重试。", "danger")
        regular_dishes = []
    return render_template('customer/index.html', regular_dishes=regular_dishes)


@app.route('/admin')
def admin_index(): # ... (不变)
    tmpl = os.path.join('templates', 'index.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login(): # ... (不变)
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username'); password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember') == 'on')
            session.permanent = True
            next_page = request.args.get('next'); flash(f'欢迎回来, {user.username}!', 'success')
            return redirect(next_page or url_for('dashboard'))
        else: flash('用户名或密码错误', 'danger')
    tmpl = os.path.join('templates', 'login.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout(): # ... (不变)
    logout_user(); flash('您已成功注销', 'info')
    return redirect(url_for('admin_index'))

@app.route('/dashboard')
@login_required
def dashboard(): # ... (不变)
    today_start_utc = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end_utc = today_start_utc + timedelta(days=1) - timedelta(microseconds=1)
    today_orders_q = Order.query.filter(Order.created_at.between(today_start_utc, today_end_utc))
    today_orders_count = today_orders_q.count()
    today_sales = db.session.query(db.func.sum(Order.final_amount))\
                           .filter(Order.created_at.between(today_start_utc, today_end_utc), Order.status == 'completed')\
                           .scalar() or 0.0
    low_stock = Ingredient.query.filter(Ingredient.quantity <= Ingredient.min_quantity).all() if current_user.role in ['owner', 'storage'] else []
    recent_orders = Order.query.options(db.joinedload(Order.member), db.joinedload(Order.waiter))\
                         .order_by(Order.created_at.desc()).limit(5).all()
    tmpl = os.path.join('templates', 'dashboard.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('dashboard.html', today_orders=today_orders_count, today_sales=today_sales, low_stock=low_stock, recent_orders=recent_orders)


# --- 销售管理 (不变) ---
# ... (menu_list, menu_add, handle_edit_dish, toggle_dish_status routes) ...
@app.route('/menu')
@login_required
@role_required(['owner', 'chef'])
def menu_list():
    dishes = Dish.query.order_by(Dish.category, Dish.name).all()
    tmpl = os.path.join('templates', 'menu_list.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('menu_list.html', dishes=dishes)

@app.route('/menu/add', methods=['GET', 'POST'])
@login_required
@role_required(['owner', 'chef'])
def menu_add():
    if request.method == 'POST':
        name = request.form.get('name'); category = request.form.get('category')
        price_str = request.form.get('price'); cost_str = request.form.get('cost')
        description = request.form.get('description')
        heritage_history = request.form.get('heritage_history') if category == 'heritage' else None
        image_url = request.form.get('image_url'); ingredients_json = request.form.get('ingredients')
        errors = {}
        if not name: errors['name'] = '名称不能为空'
        try: price = float(price_str); assert price >= 0
        except: errors['price'] = '价格无效'
        try: cost = float(cost_str); assert cost >= 0
        except: errors['cost'] = '成本无效'
        if category not in ['regular', 'heritage']: errors['category'] = '类别无效'
        if errors:
            for msg in errors.values(): flash(msg, 'danger')
            return render_template('menu_add.html', **request.form)
        dish = Dish(name=name, category=category, price=price, cost=cost, description=description, heritage_history=heritage_history, image_url=image_url, ingredients=ingredients_json)
        try:
            db.session.add(dish); db.session.commit()
            flash(f'菜品 "{name}" 添加成功', 'success'); return redirect(url_for('menu_list'))
        except Exception as e:
            db.session.rollback(); flash(f'添加失败: {e}', 'danger')
            return render_template('menu_add.html', **request.form)
    tmpl = os.path.join('templates', 'menu_add.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('menu_add.html')

@app.route('/menu/edit', methods=['POST'])
@login_required
@role_required(['owner', 'chef'])
def handle_edit_dish():
    dish_id = request.form.get('dish_id')
    if not dish_id:
        flash('未提供菜品ID', 'danger')
        return redirect(url_for('menu_list'))
    try:
        dish_id_int = int(dish_id)
        dish = Dish.query.get_or_404(dish_id_int)
        if dish.category == 'diy':
            flash('DIY 饮品记录不能在此编辑', 'warning')
            return redirect(url_for('menu_list'))
        name = request.form.get('name'); category = request.form.get('category')
        price_str = request.form.get('price'); cost_str = request.form.get('cost')
        description = request.form.get('description')
        heritage_history = request.form.get('heritage_history') if category == 'heritage' else None
        is_available_str = request.form.get('is_available')
        errors = {}
        if not name: errors['name'] = '名称不能为空'
        try: price = float(price_str); assert price >= 0
        except: errors['price'] = '价格无效'
        try: cost = float(cost_str); assert cost >= 0
        except: errors['cost'] = '成本无效'
        if category not in ['regular', 'heritage']: errors['category'] = '类别无效'
        if errors:
            for msg in errors.values(): flash(msg, 'danger')
            return redirect(url_for('menu_list'))
        dish.name = name; dish.category = category; dish.price = price; dish.cost = cost
        dish.description = description; dish.heritage_history = heritage_history
        dish.is_available = True if is_available_str == 'on' else False
        dish.updated_at = datetime.utcnow()
        if category != 'heritage': dish.heritage_history = None
        db.session.commit()
        flash(f'菜品 "{dish.name}" 更新成功', 'success')
    except ValueError: flash('无效的菜品ID格式', 'danger')
    except Exception as e:
        db.session.rollback(); flash(f'更新失败: {str(e)}', 'danger')
        print(f"Error editing dish POST {dish_id}: {e}")
    return redirect(url_for('menu_list'))

@app.route('/menu/toggle_status', methods=['POST'])
@login_required
@role_required(['owner', 'chef'])
def toggle_dish_status():
    dish_id = request.form.get('dish_id')
    if not dish_id: flash('缺少ID', 'danger'); return redirect(url_for('menu_list'))
    try:
        dish = Dish.query.get_or_404(int(dish_id))
        if dish.category == 'diy': flash('不能直接操作DIY饮品记录', 'warning')
        else:
            dish.is_available = not dish.is_available; dish.updated_at = datetime.utcnow()
            db.session.commit(); status = '上架' if dish.is_available else '下架'
            flash(f"菜品 '{dish.name}' 已成功 {status}", 'success')
    except Exception as e: db.session.rollback(); flash(f'操作失败: {e}', 'danger')
    return redirect(url_for('menu_list'))

@app.route('/menu/delete', methods=['POST'])
@login_required
@role_required(['owner']) # Only owner can delete dishes
def delete_dish():
    dish_id = request.form.get('dish_id')
    if not dish_id:
        flash('未提供菜品ID', 'danger')
        return redirect(url_for('menu_list'))
    try:
        dish_id_int = int(dish_id)
        dish = Dish.query.get_or_404(dish_id_int)
        dish_name = dish.name; category = dish.category
        if category == 'diy':
             flash('不能删除系统生成的DIY饮品记录', 'warning'); return redirect(url_for('menu_list'))
        item_count = OrderItem.query.filter_by(dish_id=dish.id).count()
        if item_count > 0:
            flash(f'无法删除菜品 "{dish_name}"，因为它存在于 {item_count} 个订单项中。', 'warning'); return redirect(url_for('menu_list'))
        db.session.delete(dish); db.session.commit()
        flash(f'菜品 "{dish_name}" 已成功删除', 'success')
    except ValueError: flash('无效的菜品ID格式', 'danger')
    except Exception as e:
        db.session.rollback(); flash(f'删除菜品时出错: {str(e)}', 'danger')
        print(f"Error deleting dish {dish_id}: {e}")
    return redirect(url_for('menu_list'))


# --- 订单管理 (不变) ---
# ... (order_list, order_create, order_detail, update_order_status, delete_order routes) ...
@app.route('/orders')
@login_required
@role_required(['owner', 'waiter', 'chef'])
def order_list():
    page = request.args.get('page', 1, type=int); per_page = 15
    pagination = Order.query.options(db.joinedload(Order.member), db.joinedload(Order.waiter))\
                        .order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items
    tmpl = os.path.join('templates', 'order_list.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('order_list.html', orders=orders, pagination=pagination)

@app.route('/orders/create', methods=['GET', 'POST'])
@login_required
@role_required(['owner', 'waiter'])
def order_create():
    if request.method == 'POST':
        member_phone = request.form.get('member_phone')
        items_json = request.form.get('items')
        diy_drink_json = request.form.get('diy_drink')
        payment_method = request.form.get('payment_method', 'cash')
        member = None; member_id = None
        if member_phone:
            member = Member.query.filter_by(phone=member_phone).first()
            if member: member_id = member.id
            else: flash(f'手机号 {member_phone} 非会员', 'warning')
        if not items_json and not diy_drink_json:
            flash('订单不能为空', 'danger'); return redirect(url_for('order_create'))
        try:
            order = Order(order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}", member_id=member_id, waiter_id=current_user.id, payment_method=payment_method, status='pending')
            db.session.add(order)
            total_amount = 0.0
            if items_json:
                try:
                    items = json.loads(items_json)
                    if not isinstance(items, list): raise ValueError("Items JSON invalid")
                    for item_data in items:
                        dish_id = item_data.get('dish_id'); quantity = int(item_data.get('quantity', 1))
                        if not dish_id or quantity <= 0: continue
                        dish = Dish.query.get(dish_id)
                        if not dish or not dish.is_available: continue
                        price = dish.price; total_amount += price * quantity
                        order_item = OrderItem(order=order, dish_id=dish.id, quantity=quantity, price=price, special_request=item_data.get('special_request'))
                        db.session.add(order_item)
                except Exception as items_error: raise ValueError(f"订单项处理出错: {items_error}")
            if diy_drink_json:
                try:
                    diy_drink = json.loads(diy_drink_json)
                    if not isinstance(diy_drink, dict) or 'base' not in diy_drink or 'sweetener' not in diy_drink: raise ValueError("DIY数据格式无效")
                    base_name = diy_drink.get('base', {}).get('name', '?'); sweetener_name = diy_drink.get('sweetener', {}).get('name', '?')
                    toppings_names = [t.get('name', '?') for t in diy_drink.get('toppings', []) if isinstance(t, dict)]
                    diy_name = f"DIY({base_name}+{sweetener_name})" + (f"+{','.join(toppings_names)}" if toppings_names else "")
                    price = float(diy_drink.get('totalPrice', 0))
                    if price <= 0: price = 15.0
                    cost = price * 0.5
                    diy_dish = Dish(name=diy_name, category='diy', price=price, cost=cost, description=json.dumps(diy_drink, ensure_ascii=False), is_available=True)
                    db.session.add(diy_dish); db.session.flush()
                    if not diy_dish.id: raise Exception("无法创建DIY临时菜品")
                    order_item = OrderItem(order=order, dish_id=diy_dish.id, quantity=1, price=price, special_request="DIY饮品")
                    db.session.add(order_item); total_amount += price
                except Exception as diy_error: raise ValueError(f"DIY饮品处理出错: {diy_error}")
            discount = 0.0; sms_to_send = None
            if member:
                if member.is_anniversary(): discount = total_amount * 0.4; sms_to_send = f"{member.name}，纪念日6折！(订单:{order.order_number})"
                elif member.points >= 100: discount = total_amount * 0.4; member.points = 0; sms_to_send = f"{member.name}，100积分抵扣6折！(订单:{order.order_number})"
                else: points_earned = int(total_amount); member.points += points_earned; sms_to_send = f"{member.name}，获{points_earned}积分。(订单:{order.order_number})"
                member.last_visit = datetime.utcnow(); db.session.add(member)
            order.total_amount = round(total_amount, 2); order.discount = round(discount, 2)
            order.final_amount = round(max(0, total_amount - discount), 2)
            db.session.commit()
            flash('订单创建成功', 'success')
            if sms_to_send and member: send_sms(member.phone, sms_to_send)
            return redirect(url_for('order_detail', order_id=order.id))
        except Exception as e:
            db.session.rollback(); flash(f'创建订单时发生错误: {str(e)}', 'danger')
            print(f"ERROR during order creation POST: {e}")
            return redirect(url_for('order_create'))
    dishes = Dish.query.filter(Dish.is_available == True, Dish.category == 'regular').all()
    heritage_dishes = Dish.query.filter(Dish.is_available == True, Dish.category == 'heritage').all()
    members = Member.query.order_by(Member.name).all()
    tmpl = os.path.join('templates', 'order_create.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('order_create.html', dishes=dishes, heritage_dishes=heritage_dishes, members=members)

@app.route('/orders/<int:order_id>')
@login_required
@role_required(['owner', 'waiter', 'chef'])
def order_detail(order_id):
    order = Order.query.options(db.joinedload(Order.items).joinedload(OrderItem.dish), db.joinedload(Order.member), db.joinedload(Order.waiter)).get_or_404(order_id)
    tmpl = os.path.join('templates', 'order_detail.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('order_detail.html', order=order)

@app.route('/orders/<int:order_id>/update_status', methods=['POST'])
@login_required
@role_required(['owner', 'waiter', 'chef'])
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id); status = request.form.get('status')
    valid = ['pending', 'cooking', 'completed', 'cancelled']
    if status in valid:
        if order.status in ['completed', 'cancelled'] and status != order.status: flash(f'订单已{order.status}，无法修改', 'warning')
        else:
            order.status = status; order.updated_at = datetime.utcnow()
            try:
                db.session.commit(); flash(f'订单状态更新为: {status}', 'success')
                if status in ['completed', 'cancelled'] and order.member: send_order_notification(order.member.phone, order.member.name, order.order_number, status)
            except Exception as e: db.session.rollback(); flash(f'更新失败: {e}', 'danger')
    else: flash('无效状态', 'danger')
    return redirect(url_for('order_detail', order_id=order.id))

@app.route('/orders/delete', methods=['POST'])
@login_required
@role_required(['owner'])
def delete_order():
    order_id = request.form.get('order_id')
    if not order_id: flash('缺少ID', 'danger'); return redirect(url_for('order_list'))
    try:
        order = Order.query.get_or_404(int(order_id))
        db.session.delete(order); db.session.commit(); flash('订单删除成功', 'success')
    except Exception as e: db.session.rollback(); flash(f'删除失败: {e}', 'danger')
    return redirect(url_for('order_list'))

# --- 会员管理 (不变) ---
# ... (member_list, member_add, member_detail routes) ...
@app.route('/members')
@login_required
@role_required(['owner', 'waiter'])
def member_list():
    page = request.args.get('page', 1, type=int); per_page = 15; search = request.args.get('search', '')
    query = Member.query
    if search: query = query.filter(db.or_(Member.name.like(f'%{search}%'), Member.phone.like(f'%{search}%')))
    pagination = query.order_by(Member.join_date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    members = pagination.items
    tmpl = os.path.join('templates', 'member_list.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('member_list.html', members=members, pagination=pagination, search_term=search)

@app.route('/members/add', methods=['GET', 'POST'])
@login_required
@role_required(['owner', 'waiter'])
def member_add():
    if request.method == 'POST':
        name = request.form.get('name'); phone = request.form.get('phone'); email = request.form.get('email')
        errors = {}
        if not name: errors['name'] = '姓名不能为空'
        if not phone or not phone.isdigit() or len(phone) < 7: errors['phone'] = '手机号无效'
        elif Member.query.filter_by(phone=phone).first(): errors['phone'] = '手机号已注册'
        if errors:
            for msg in errors.values(): flash(msg, 'danger')
            return render_template('member_add.html', **request.form)
        try:
            member = Member(name=name, phone=phone, email=email if email else None)
            db.session.add(member); db.session.commit()
            send_member_welcome(phone, name)
            flash('会员添加成功', 'success'); return redirect(url_for('member_list'))
        except Exception as e: db.session.rollback(); flash(f'添加失败: {e}', 'danger')
    tmpl = os.path.join('templates', 'member_add.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('member_add.html')

@app.route('/members/<int:member_id>')
@login_required
@role_required(['owner', 'waiter'])
def member_detail(member_id):
    member = Member.query.get_or_404(member_id)
    page = request.args.get('page', 1, type=int); per_page = 10
    pagination = Order.query.filter_by(member_id=member_id)\
                        .options(db.joinedload(Order.items).joinedload(OrderItem.dish))\
                        .order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    orders = pagination.items
    tmpl = os.path.join('templates', 'member_detail.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('member_detail.html', member=member, orders=orders, pagination=pagination)

# --- 顾客会员注册 (不变) ---
# ... (customer_register route) ...
@app.route('/customer/register', methods=['GET', 'POST'])
def customer_register():
    if request.method == 'POST':
        name = request.form.get('name'); phone = request.form.get('phone'); email = request.form.get('email'); agree = request.form.get('agreeTerms')
        errors = {}
        if not name: errors['name'] = '姓名不能为空'
        if not phone or not phone.isdigit() or len(phone) < 7: errors['phone'] = '手机号无效'
        elif Member.query.filter_by(phone=phone).first(): errors['phone'] = '手机号已注册'
        if not agree: errors['agree'] = '请同意条款'
        if errors:
            for msg in errors.values(): flash(msg, 'danger')
            return render_template('customer/register.html', **request.form)
        try:
            member = Member(name=name, phone=phone, email=email if email else None)
            db.session.add(member); db.session.commit()
            send_member_welcome(phone, name)
            flash('注册成功！', 'success'); return redirect(url_for('customer_index'))
        except Exception as e: db.session.rollback(); flash(f'注册失败: {e}', 'danger')
    tmpl = os.path.join('templates', 'customer', 'register.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('customer/register.html')

# --- 库存管理 (不变) ---
# ... (inventory_list, inventory_add, update_inventory, delete_inventory, check_stock routes) ...
@app.route('/inventory')
@login_required
@role_required(['owner', 'storage'])
def inventory_list():
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    tmpl = os.path.join('templates', 'inventory_list.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('inventory_list.html', ingredients=ingredients)

@app.route('/inventory/add', methods=['GET', 'POST'])
@login_required
@role_required(['owner', 'storage'])
def inventory_add():
    if request.method == 'POST':
        name = request.form.get('name'); unit = request.form.get('unit')
        qty_s = request.form.get('quantity'); min_qty_s = request.form.get('min_quantity')
        price_s = request.form.get('price_per_unit'); expiry_s = request.form.get('expiry_date')
        errors = {}
        qty = 0.0; min_qty = 0.0; price = 0.0; expiry_d = None # Initialize
        if not name: errors['name'] = '名称不能为空'
        elif Ingredient.query.filter_by(name=name).first(): errors['name'] = f'"{name}" 已存在'
        if not unit: errors['unit'] = '单位不能为空'
        try: qty = float(qty_s); assert qty >= 0
        except: errors['quantity'] = '数量无效'
        try: min_qty = float(min_qty_s); assert min_qty >= 0
        except: errors['min_quantity'] = '最低库存无效'
        try: price = float(price_s); assert price >= 0
        except: errors['price_per_unit'] = '单价无效'
        if expiry_s:
            try: expiry_d = datetime.strptime(expiry_s, '%Y-%m-%d')
            except ValueError: errors['expiry_date'] = '日期格式需为YYYY-MM-DD 格式'
        if errors:
            for msg in errors.values(): flash(msg, 'danger')
            return render_template('inventory_add.html', **request.form)
        try:
            ingredient = Ingredient(name=name, unit=unit, quantity=qty, min_quantity=min_qty, price_per_unit=price, expiry_date=expiry_d)
            db.session.add(ingredient); db.session.commit()
            flash('原料添加成功', 'success'); return redirect(url_for('inventory_list'))
        except Exception as e: db.session.rollback(); flash(f'添加失败: {e}', 'danger')
    tmpl = os.path.join('templates', 'inventory_add.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('inventory_add.html')

@app.route('/inventory/update', methods=['POST'])
@login_required
@role_required(['owner', 'storage'])
def update_inventory():
    ing_id = request.form.get('ingredient_id'); qty_s = request.form.get('quantity'); action = request.form.get('action', 'set')
    if not ing_id or qty_s is None: flash('缺少参数', 'danger'); return redirect(url_for('inventory_list'))
    try:
        ing = Ingredient.query.get_or_404(int(ing_id)); qty = float(qty_s)
        orig_qty = ing.quantity
        if action == 'add': ing.quantity += qty
        elif action == 'subtract': ing.quantity = max(0, ing.quantity - qty)
        else: ing.quantity = max(0, qty)
        db.session.commit(); flash(f'"{ing.name}" 库存更新成功', 'success')
        if ing.is_low_stock():
            owner = User.query.filter_by(role='owner').first()
            if owner and owner.phone: send_low_stock_alert(owner.phone, ing.name, ing.quantity)
    except ValueError: flash('数量必须是数字', 'danger')
    except Exception as e: db.session.rollback(); flash(f'更新失败: {e}', 'danger')
    return redirect(url_for('inventory_list'))

@app.route('/inventory/delete', methods=['POST'])
@login_required
@role_required(['owner'])
def delete_inventory():
    ing_id = request.form.get('ingredient_id')
    if not ing_id: flash('缺少ID', 'danger'); return redirect(url_for('inventory_list'))
    try:
        ing = Ingredient.query.get_or_404(int(ing_id))
        name = ing.name; db.session.delete(ing); db.session.commit(); flash(f'"{name}" 已删除', 'success')
    except Exception as e: db.session.rollback(); flash(f'删除失败: {e}', 'danger')
    return redirect(url_for('inventory_list'))

@app.route('/inventory/check_stock')
@login_required
@role_required(['owner', 'storage'])
def check_stock():
    low_stock = Ingredient.query.filter(Ingredient.quantity <= Ingredient.min_quantity).all()
    tmpl = os.path.join('templates', 'inventory_low_stock.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('inventory_low_stock.html', low_stock=low_stock)


# --- 特色功能 (不变) ---
# ... (heritage_dishes, diy_drinks, check_compatibility, init_diy_data routes) ...
@app.route('/heritage_dishes')
def heritage_dishes():
    dishes = Dish.query.filter_by(category='heritage', is_available=True).order_by(Dish.name).all()
    tmpl = os.path.join('templates', 'heritage_dishes.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('heritage_dishes.html', dishes=dishes)

@app.route('/diy_drinks')
def diy_drinks():
    bases = IngredientOption.query.filter_by(category='base', is_available=True).all()
    sweeteners = IngredientOption.query.filter_by(category='sweetener', is_available=True).all()
    toppings = IngredientOption.query.filter_by(category='topping', is_available=True).all()
    tmpl = os.path.join('templates', 'diy_drinks.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('diy_drinks.html', bases=bases, sweeteners=sweeteners, toppings=toppings)

@app.route('/api/check_compatibility', methods=['POST'])
@rate_limit(max_calls=20, period=60)
def check_compatibility():
    if not request.is_json: return jsonify({'error': 'Request must be JSON'}), 400
    data = request.get_json(); ids = data.get('ingredient_ids', [])
    if not isinstance(ids, list): return jsonify({'error': 'ids must be a list'}), 400
    opts = IngredientOption.query.filter(IngredientOption.id.in_(ids)).all()
    opts_d = {opt.id: opt for opt in opts}; incompatible = []; processed = set()
    for id1 in ids:
        opt1 = opts_d.get(id1)
        if not opt1 or not opt1.incompatible_with or opt1.incompatible_with == '[]': continue
        try: incompatible_ids = set(int(i) for i in json.loads(opt1.incompatible_with))
        except: continue
        for id2 in ids:
            if id1 == id2: continue
            pair = tuple(sorted((id1, id2)));
            if pair in processed: continue; processed.add(pair)
            if id2 in incompatible_ids:
                opt2 = opts_d.get(id2)
                if opt2: incompatible.append({'id1':id1, 'name1':opt1.name, 'id2':id2, 'name2':opt2.name})
    if incompatible: return jsonify({'compatible': False, 'message': '部分搭配冲突', 'incompatible_pairs': incompatible})
    else: return jsonify({'compatible': True, 'message': '搭配OK！'})

@app.route('/init_diy_data')
@login_required
@role_required(['owner'])
def init_diy_data():
     if IngredientOption.query.count() > 0:
        flash('DIY配料数据已存在。', 'warning')
     else:
        try:
            bases_data = [{'name':'绿茶','category':'base','price':8.0,'description': '清爽','incompatible_with':'[]'}, {'name':'红茶','category':'base','price':8.0,'description':'浓郁','incompatible_with':'[]'}, {'name':'乌龙茶','category':'base','price':9.0,'description':'丰富','incompatible_with':'[]'}, {'name':'椰奶','category':'base','price':10.0,'description':'椰香','incompatible_with':'[]'}, {'name':'鲜奶','category':'base','price':10.0,'description':'奶香','incompatible_with':'[]'}, {'name':'柠檬汁底','category':'base','price':7.0,'description':'酸爽','incompatible_with':'[]'}]
            sweets_data = [{'name':'白砂糖','category':'sweetener','price':1.0,'description':'标准','incompatible_with':'[]'}, {'name':'蜂蜜','category':'sweetener','price':3.0,'description':'天然','incompatible_with':'[]'}, {'name':'炼乳','category':'sweetener','price':2.0,'description':'奶甜','incompatible_with':'[]'}, {'name':'无糖','category':'sweetener','price':0.0,'description':'无糖','incompatible_with':'[]'}]
            tops_data = [{'name':'珍珠','category':'topping','price':3.0,'description':'Q弹','incompatible_with':'[]'}, {'name':'布丁','category':'topping','price':4.0,'description':'滑嫩','incompatible_with':'[]'}, {'name':'芋圆','category':'topping','price':4.0,'description':'香糯','incompatible_with':'[]'}, {'name':'椰果','category':'topping','price':3.0,'description':'爽脆','incompatible_with':'[]'}, {'name':'奶盖','category':'topping','price':6.0,'description':'咸香','incompatible_with':'[]'}, {'name':'芒果粒','category':'topping','price':5.0,'description':'新鲜','incompatible_with':'[]'}, {'name':'西米','category':'topping','price':3.0,'description':'透明','incompatible_with':'[]'}, {'name':'柠檬片(装饰)','category':'topping','price':2.0,'description':'装饰','incompatible_with':'[]'}, {'name':'草莓粒','category':'topping','price':5.0,'description':'新鲜','incompatible_with':'[]'}, {'name':'薄荷叶(装饰)','category':'topping','price':2.0,'description':'清凉','incompatible_with':'[]'}]
            all_opts_data = bases_data + sweets_data + tops_data
            db.session.bulk_insert_mappings(IngredientOption, [{'name':d['name'],'category':d['category'],'price':d['price'], 'description':d.get('description',''), 'incompatible_with':d.get('incompatible_with','[]')} for d in all_opts_data]);
            db.session.commit()
            opts_map = {opt.name: opt.id for opt in IngredientOption.query.all()}
            updates = {"椰奶":["奶盖"],"鲜奶":["奶盖"],"柠檬汁底":["椰奶","鲜奶","奶盖"],"奶盖":["椰奶","鲜奶","柠檬汁底"],"柠檬片(装饰)":["椰奶","鲜奶","奶盖"]}
            for name, incompat_names in updates.items():
                opt = IngredientOption.query.filter_by(name=name).first()
                if opt: opt.incompatible_with = json.dumps([opts_map.get(n) for n in incompat_names if opts_map.get(n)])
            db.session.commit()
            flash('DIY数据初始化成功', 'success')
        except Exception as e: db.session.rollback(); flash(f'初始化失败: {e}', 'danger')
     return redirect(url_for('diy_drinks'))

# --- 错误处理 (不变) ---
# ... (page_not_found, internal_server_error handlers) ...
@app.errorhandler(404)
def page_not_found(e):
    tmpl = os.path.join('templates', '404.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    db.session.rollback(); print(f"Internal Server Error: {e}") # Log the error
    tmpl = os.path.join('templates', '500.html')
    if not os.path.exists(tmpl): create_placeholder_template(tmpl)
    return render_template('500.html'), 500

# --- 初始化与运行 (移除 app.run) ---
def create_placeholder_template(filepath): # ... (不变)
    try:
        dirname = os.path.dirname(filepath)
        if dirname: os.makedirs(dirname, exist_ok=True)
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f: f.write(f'<!DOCTYPE html><html><head><title>Placeholder: {os.path.basename(filepath)}</title></head><body><h1>{os.path.basename(filepath)}</h1></body></html>')
            print(f"Created placeholder: {filepath}")
    except Exception as e: print(f"Error creating placeholder {filepath}: {e}")

def create_tables_and_admin(): # ... (包含数据初始化，不变) ...
     with app.app_context():
        print("初始化数据库...")
        db.create_all()
        print("数据库表完成。")
        # ... (User init) ...
        initial_users = {
            'admin': {'email': 'admin@example.com', 'role': 'owner', 'password': 'admin123', 'phone': '13800138000'},
            'chef1': {'email': 'chef1@example.com', 'role': 'chef', 'password': 'chef123', 'phone': '13800138001'},
            'waiter1': {'email': 'waiter1@example.com', 'role': 'waiter', 'password': 'waiter123', 'phone': '13800138002'},
            'storage1': {'email': 'storage1@example.com', 'role': 'storage', 'password': 'storage123', 'phone': '13800138003'}
        }
        count = 0
        for uname, udata in initial_users.items():
            if not User.query.filter_by(username=uname).first():
                user = User(username=uname, **{k:v for k,v in udata.items() if k != 'password'})
                user.set_password(udata['password']); db.session.add(user); count += 1
        if count > 0:
            try:
                db.session.commit(); print(f"成功添加了 {count} 个初始用户。")
            except Exception as e: db.session.rollback(); print(f"添加初始用户时出错: {e}")
        else: print("用户已存在。")

        # ... (Dish init) ...
        if Dish.query.count() == 0:
            print("Dish 表为空，开始添加初始菜品数据...")
            try:
                initial_dishes = [
                    {'name': '兰州牛肉面', 'category': 'heritage', 'price': 15.0, 'cost': 7.0, 'description': '汤清肉烂', 'heritage_history': '源于清代', 'is_available': True},
                    {'name': '手抓羊肉', 'category': 'heritage', 'price': 78.0, 'cost': 40.0, 'description': '鲜嫩多汁', 'heritage_history': '西北特色', 'is_available': True},
                    {'name': '浆水面', 'category': 'heritage', 'price': 12.0, 'cost': 5.0, 'description': '酸香开胃', 'heritage_history': '定西家常', 'is_available': True},
                    {'name': '定西宽粉（炒）', 'category': 'heritage', 'price': 18.0, 'cost': 8.0, 'description': '爽滑筋道', 'heritage_history': '地方特产', 'is_available': True},
                    {'name': '农家小炒肉', 'category': 'regular', 'price': 25.0, 'cost': 12.0, 'description': '香辣下饭', 'is_available': True},
                    {'name': '西红柿炒鸡蛋', 'category': 'regular', 'price': 15.0, 'cost': 6.0, 'description': '国民家常', 'is_available': True},
                    {'name': '鱼香肉丝', 'category': 'regular', 'price': 28.0, 'cost': 13.0, 'description': '川菜经典', 'is_available': True},
                    {'name': '麻婆豆腐', 'category': 'regular', 'price': 18.0, 'cost': 7.0, 'description': '麻辣鲜香', 'is_available': True},
                    {'name': '清炒油麦菜', 'category': 'regular', 'price': 12.0, 'cost': 5.0, 'description': '清淡爽口', 'is_available': True},
                    {'name': '红烧肉', 'category': 'regular', 'price': 38.0, 'cost': 18.0, 'description': '肥而不腻', 'is_available': False},
                    {'name': '土豆牛肉盖饭', 'category': 'regular', 'price': 22.0, 'cost': 11.0, 'description': '快捷实惠', 'is_available': True},
                    {'name': '宫保鸡丁盖饭', 'category': 'regular', 'price': 20.0, 'cost': 9.0, 'description': '咸鲜带辣', 'is_available': True},
                ]
                db.session.bulk_insert_mappings(Dish, initial_dishes); db.session.commit()
                print(f"成功添加了 {len(initial_dishes)} 个初始菜品。")
            except Exception as e: db.session.rollback(); print(f"添加初始菜品时出错: {e}")
        else: print("Dish数据已存在。")

        # ... (Ingredient init) ...
        if Ingredient.query.count() == 0:
            print("Ingredient 表为空，开始添加初始原料数据...")
            try:
                initial_ingredients = [
                    {'name': '大米', 'unit': '公斤', 'quantity': 50.0, 'min_quantity': 10.0, 'price_per_unit': 6.0},
                    {'name': '面粉', 'unit': '公斤', 'quantity': 40.0, 'min_quantity': 10.0, 'price_per_unit': 5.0},
                    {'name': '猪五花肉', 'unit': '公斤', 'quantity': 25.0, 'min_quantity': 5.0, 'price_per_unit': 30.0},
                    {'name': '牛肉(普通)', 'unit': '公斤', 'quantity': 12.0, 'min_quantity': 4.0, 'price_per_unit': 50.0},
                    {'name': '羊肋排', 'unit': '公斤', 'quantity': 8.0, 'min_quantity': 2.0, 'price_per_unit': 65.0},
                    {'name': '鸡胸肉', 'unit': '公斤', 'quantity': 20.0, 'min_quantity': 5.0, 'price_per_unit': 20.0},
                    {'name': '鸡蛋', 'unit': '个', 'quantity': 100.0, 'min_quantity': 30.0, 'price_per_unit': 1.0},
                    {'name': '土豆', 'unit': '公斤', 'quantity': 30.0, 'min_quantity': 10.0, 'price_per_unit': 4.0},
                    {'name': '西红柿', 'unit': '公斤', 'quantity': 15.0, 'min_quantity': 5.0, 'price_per_unit': 8.0},
                    {'name': '青椒', 'unit': '公斤', 'quantity': 10.0, 'min_quantity': 3.0, 'price_per_unit': 10.0},
                    {'name': '油麦菜', 'unit': '公斤', 'quantity': 8.0, 'min_quantity': 2.0, 'price_per_unit': 9.0},
                    {'name': '豆腐', 'unit': '块', 'quantity': 20.0, 'min_quantity': 5.0, 'price_per_unit': 2.5},
                    {'name': '食用油', 'unit': '升', 'quantity': 20.0, 'min_quantity': 5.0, 'price_per_unit': 12.0},
                    {'name': '酱油', 'unit': '升', 'quantity': 10.0, 'min_quantity': 2.0, 'price_per_unit': 15.0},
                    {'name': '盐', 'unit': '公斤', 'quantity': 5.0, 'min_quantity': 1.0, 'price_per_unit': 4.0},
                    {'name': '可乐', 'unit': '瓶', 'quantity': 5.0, 'min_quantity': 10.0, 'price_per_unit': 3.0},
                ]
                db.session.bulk_insert_mappings(Ingredient, initial_ingredients); db.session.commit()
                print(f"成功添加了 {len(initial_ingredients)} 个初始原料。")
            except Exception as e: db.session.rollback(); print(f"添加初始原料时出错: {e}")
        else: print("Ingredient数据已存在。")

        # ... (DIY Option init - unchanged) ...
        if IngredientOption.query.count() == 0:
             print("初始化DIY配料...")
             try:
                # ... (DIY data and logic) ...
                 print("DIY配料和关系初始化完成。")
             except Exception as e: db.session.rollback(); print(f"DIY初始化失败: {e}")
        else: print("DIY数据已存在。")


def ensure_templates_dir(): # ... (不变)
    if not os.path.exists('templates'): os.makedirs('templates'); print("Created 'templates'")
    if not os.path.exists('templates/customer'): os.makedirs('templates/customer'); print("Created 'templates/customer'")

@app.context_processor
def inject_now(): # ... (不变)
    return {'now': datetime.utcnow()}

# --- !! 修改：移除 app.run() !! ---
if __name__ == '__main__':
    ensure_templates_dir()
    # required_templates = [...] # 保持不变
    # for tmpl in required_templates: create_placeholder_template(os.path.join('templates', tmpl)) # 保持不变
    required_templates = ['index.html', 'login.html', 'dashboard.html', 'menu_list.html', 'menu_add.html','menu_edit.html', 'order_list.html', 'order_create.html', 'order_detail.html','member_list.html', 'member_add.html', 'member_detail.html','inventory_list.html', 'inventory_add.html', 'inventory_low_stock.html','heritage_dishes.html', 'diy_drinks.html', '404.html', '500.html','customer/index.html', 'customer/register.html', 'base_admin.html']
    for tmpl in required_templates: create_placeholder_template(os.path.join('templates', tmpl))
    print("模板文件检查/创建完成。")
    try:
        create_tables_and_admin() # 包含数据初始化
    except Exception as e:
        print(f"数据库初始化失败: {e}")

    print("数据库和初始数据设置完成。")
    print("要运行开发服务器，请使用 'flask run' 命令。")
    print("要进行生产部署，请使用 Waitress 或 Gunicorn 等 WSGI 服务器。")
    # app.run(debug=True, host='0.0.0.0', port=5000) # <-- 确保此行被删除或注释掉
# --- !! 修改结束 !! ---123
