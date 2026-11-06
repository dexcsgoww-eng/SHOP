from aiogram.fsm.state import State, StatesGroup

class AddCategory(StatesGroup):
    name = State()
    emoji = State()
    description = State()
    image = State()

class EditCategory(StatesGroup):
    value = State()

class AddProduct(StatesGroup):
    name = State()
    description = State()
    price = State()
    image = State()

class EditProduct(StatesGroup):
    value = State()

class UploadItems(StatesGroup):
    items = State()

class Broadcast(StatesGroup):
    message = State()
    confirm = State()

class EditText(StatesGroup):
    value = State()

class EditImage(StatesGroup):
    value = State()

class Withdraw(StatesGroup):
    method = State()
    address = State()
    amount = State()

class AdminWithdraw(StatesGroup):
    comment = State()

class UserManage(StatesGroup):
    user_id = State()
    amount = State()

class TopUp(StatesGroup):
    amount = State()

class ManualTopUp(StatesGroup):
    amount = State()
    proof = State()

class ManualProduct(StatesGroup):
    proof = State()

class EditButton(StatesGroup):
    icon = State()

class AddSubChannel(StatesGroup):
    data = State()

class SubInvite(StatesGroup):
    link = State()

class AddPromocode(StatesGroup):
    code = State()
    ptype = State()
    amount = State()
    max_uses = State()
    min_purchase = State()
    expires_days = State()

class UsePromocode(StatesGroup):
    code = State()

class AddSectionButton(StatesGroup):
    text = State()
    data = State()

class EditSectionButton(StatesGroup):
    value = State()
