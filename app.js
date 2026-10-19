// Taom ma’lumotlarini mavjud HTML kartochkalaridan olish.
const cards = [...document.querySelectorAll(".products .card")];
const search = document.querySelector('.search input');
const categoryContainer = document.querySelector('#categories');
const cart = new Map();
const cartDialog = document.querySelector('#cart');
const cartItems = document.querySelector('#cart-items');
const notice = document.querySelector('#notice');
let selectedCategory = 'Barchasi';
let noticeTimer;

function normalize(text) {
    return text.trim().toLowerCase().replace(/[‘’ʻʼ`]/g, "'");
}

function formatPrice(price) {
    return price.toLocaleString('uz-UZ') + ' so‘m';
}

let dishes = cards.map((card, index) => ({
    key: String(index + 1),
    name: card.querySelector('h3').textContent.trim(),
    category: card.querySelector('.dish-meta').textContent.split('·')[0].trim(),
    description: card.querySelector('.card-body p').textContent.trim(),
    price: Number(card.querySelector('.price').textContent.replace(/\D/g, '')),
    card,
}));

const emptyMessage = document.createElement('p');
emptyMessage.className = 'empty-message';
emptyMessage.textContent = 'Taom topilmadi. Boshqa nom yoki kategoriyani tanlang.';
document.querySelector('#products').after(emptyMessage);

// Kategoriya va qidiruv birgalikda ishlaydi.
function filterDishes() {
    const query = normalize(search.value);
    let count = 0;
    dishes.forEach((dish) => {
        const matchesCategory = selectedCategory === 'Barchasi' ||
            normalize(dish.category) === normalize(selectedCategory);
        const matchesSearch = normalize(dish.name + ' ' + dish.description).includes(query);
        dish.card.hidden = !(matchesCategory && matchesSearch);
        if (!dish.card.hidden) count++;
    });
    document.querySelector('#result').textContent = count + ' ta taom va ichimlik';
    emptyMessage.hidden = count > 0;
}

categoryContainer.addEventListener('click', (event) => {
        const button = event.target.closest('[data-category]');
        if (!button) return;
        selectedCategory = button.dataset.category;
        categoryContainer.querySelectorAll('button').forEach((item) => {
            item.classList.toggle('active', item === button);
            item.setAttribute('aria-pressed', String(item === button));
        });
        filterDishes();
});
search.addEventListener('input', filterDishes);

// Savat miqdori va jami narx.
function updateCart() {
    cartItems.replaceChildren();
    let total = 0;
    let count = 0;
    for (const [key, item] of cart) {
        total += item.price * item.quantity;
        count += item.quantity;
        const row = document.createElement('div');
        row.className = 'cart-row';
        const label = document.createElement('span');
        label.textContent = item.name + ' — ' + formatPrice(item.price * item.quantity);
        const controls = document.createElement('div');
        controls.className = 'quantity';
        const amount = document.createElement('span');
        amount.textContent = item.quantity;
        const minus = createQuantityButton('−', -1, key, item);
        const plus = createQuantityButton('+', 1, key, item);
        controls.append(minus, amount, plus);
        row.append(label, controls);
        cartItems.append(row);
    }
    if (cart.size === 0) cartItems.textContent = 'Hozircha tanlovingiz bo‘sh.';
    document.querySelector('#count').textContent = count;
    document.querySelector('#total').textContent = formatPrice(total);
}

function createQuantityButton(text, step, key, item) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = text;
    button.setAttribute('aria-label', item.name + (step > 0 ? ' sonini oshirish' : ' sonini kamaytirish'));
    button.addEventListener('click', () => {
        item.quantity += step;
        if (item.quantity === 0) cart.delete(key);
        updateCart();
    });
    return button;
}

function bindAddButtons() {
dishes.forEach((dish) => {
    dish.card.querySelector('.add').addEventListener('click', () => {
        const item = cart.get(dish.key);
        if (item) item.quantity++;
        else cart.set(dish.key, { name: dish.name, price: dish.price, quantity: 1 });
        updateCart();
        notice.textContent = dish.name + ' tanlovga qo‘shildi';
        notice.classList.add('show');
        clearTimeout(noticeTimer);
        noticeTimer = setTimeout(() => notice.classList.remove('show'), 2000);
    });
});

}

document.querySelector('#basket').addEventListener('click', () => cartDialog.showModal());
document.querySelector('#close-cart').addEventListener('click', () => cartDialog.close());
cartDialog.addEventListener('click', (event) => {
    if (event.target !== cartDialog) return;
    const box = cartDialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right ||
        event.clientY < box.top || event.clientY > box.bottom) cartDialog.close();
});

updateCart();
bindAddButtons();
filterDishes();

// Server menyusi barcha qurilmalarda bitta bazadan olinadi.
let menuVersion = '';
async function loadMenu() {
    if (!['http:', 'https:'].includes(location.protocol)) return;
    try {
        const response = await fetch('/api/dishes', { cache: 'no-store' });
        if (!response.ok) throw new Error('Menyu yuklanmadi');
        const data = await response.json();
        const categoryResponse = await fetch('/api/categories', { cache: 'no-store' });
        if (!categoryResponse.ok) throw new Error('Kategoriyalar yuklanmadi');
        const categoryNames = await categoryResponse.json();
        const version = JSON.stringify([data, categoryNames]);
        if (version === menuVersion) return;
        const template = cards[0];
        const products = document.querySelector('#products');
        const nextDishes = data.map(item => {
            const card = template.cloneNode(true);
            card.hidden = false;
            card.querySelector('.tag')?.remove();
            const image = card.querySelector('img');
            image.src = item.image;
            image.alt = item.name;
            card.querySelector('h3').textContent = item.name;
            card.querySelector('.dish-meta').textContent = item.category + (item.portion ? ' · ' + item.portion : '');
            card.querySelector('.card-body p').textContent = item.description;
            card.querySelector('.price').textContent = formatPrice(item.price);
            card.querySelector('.add').dataset.add = item.id;
            card.querySelector('.add').setAttribute('aria-label', item.name + ' — tanlovga qo‘shish');
            return { ...item, key: String(item.id), card };
        });
        dishes = nextDishes;
        products.replaceChildren(...dishes.map(dish => dish.card));
        const categories = ['Barchasi', ...new Set([...categoryNames, ...dishes.map(dish => dish.category)])];
        if (!categories.includes(selectedCategory)) selectedCategory = 'Barchasi';
        categoryContainer.replaceChildren(...categories.map(category => {
            const button = document.createElement('button');
            button.textContent = category;
            button.dataset.category = category;
            button.classList.toggle('active', category === selectedCategory);
            button.setAttribute('aria-pressed', String(category === selectedCategory));
            return button;
        }));
        for (const [key, item] of cart) {
            const current = dishes.find(dish => dish.key === key);
            if (!current) cart.delete(key);
            else { item.name = current.name; item.price = current.price; }
        }
        bindAddButtons();
        updateCart();
        filterDishes();
        menuVersion = version;
    } catch (error) {
        console.warn('Server menyusi mavjud emas:', error.message);
    }
}
loadMenu();
setInterval(() => { if (!document.hidden) loadMenu(); }, 15000);
window.addEventListener('focus', loadMenu);
