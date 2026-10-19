const login = document.querySelector('#login');
const dashboard = document.querySelector('#dashboard');
const editor = document.querySelector('#editor');
const status = document.querySelector('#status');
const logout = document.querySelector('#logout');
let csrf = null;
let dishes = [];
let editingId = null;
let currentImage = '';
let previewUrl = null;
let selectedCategory = 'Barchasi';

async function api(path, method = 'GET', data) {
    const response = await fetch(path, {
        method,
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf || '' },
        body: data === undefined ? undefined : JSON.stringify(data),
    });
    const result = await response.json();
    if (!response.ok) {
        if (response.status === 401) showSession(null);
        throw new Error(result.error || 'So‘rov bajarilmadi');
    }
    return result;
}

function showSession(token) {
    csrf = token;
    login.hidden = Boolean(token);
    dashboard.hidden = !token;
    logout.hidden = !token;
}

function resetEditor() {
    editingId = null;
    currentImage = '';
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    editor.reset();
    editor.elements.photo.setCustomValidity('');
    editor.elements.photo.required = true;
    document.querySelector('#form-title').textContent = 'Yangi taom';
    document.querySelector('#preview').hidden = true;
    updateUploadLabel();
}

function updateUploadLabel() {
    const file = editor.elements.photo.files[0];
    const hasPhoto = Boolean(file || currentImage);
    document.querySelector('.upload-card').classList.toggle('has-photo', hasPhoto);
    document.querySelector('#photo-name').textContent = file ? file.name : currentImage ? 'Mavjud rasm saqlangan' : 'Hali rasm tanlanmagan';
    document.querySelector('#photo-button').textContent = hasPhoto ? 'Rasmni almashtirish ↗' : 'Rasm tanlash ↗';
}

function preview() {
    updateUploadLabel();
    const image = document.querySelector('#preview');
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    const file = editor.elements.photo.files[0];
    editor.elements.photo.setCustomValidity('');
    if (file && (file.size > 5 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) {
        editor.elements.photo.setCustomValidity('JPG, PNG yoki WebP rasm tanlang (5 MB gacha).');
        editor.elements.photo.reportValidity();
        image.hidden = true;
        return;
    }
    if (file) previewUrl = URL.createObjectURL(file);
    const url = previewUrl || (currentImage.startsWith('images/') ? '/' + currentImage : currentImage);
    image.hidden = !url;
    if (url) image.src = url;
}

function render() {
    const list = document.querySelector('#list');
    list.replaceChildren();
    const query = document.querySelector('#search').value.toLocaleLowerCase();
    const visible = dishes.filter(d =>
        (selectedCategory === 'Barchasi' || d.category === selectedCategory) &&
        (d.name + ' ' + d.category).toLocaleLowerCase().includes(query));
    document.querySelector('#dish-count').textContent = `(${visible.length})`;
    for (const dish of visible) {
        const row = document.createElement('article');
        row.className = 'dish';
        const image = document.createElement('img');
        image.src = dish.image.startsWith('images/') ? '/' + dish.image : dish.image;
        image.alt = dish.name;
        image.loading = 'lazy';
        const info = document.createElement('div');
        info.className = 'dish-info';
        const title = document.createElement('h3');
        title.textContent = dish.name;
        const detail = document.createElement('p');
        detail.textContent = `${dish.category} · ${dish.price.toLocaleString('uz-UZ')} so‘m`;
        info.append(title, detail);
        const actions = document.createElement('div');
        actions.className = 'actions';
        const edit = document.createElement('button');
        edit.textContent = 'Tahrirlash';
        edit.className = 'secondary';
        edit.onclick = () => {
            editingId = dish.id;
            currentImage = dish.image;
            editor.elements.photo.value = '';
            editor.elements.photo.required = false;
            for (const field of ['name', 'category', 'portion', 'description', 'price']) editor.elements[field].value = dish[field];
            document.querySelector('#form-title').textContent = 'Taomni tahrirlash';
            preview();
            editor.scrollIntoView({ behavior: 'smooth', block: 'start' });
            editor.elements.name.focus({ preventScroll: true });
        };
        const remove = document.createElement('button');
        remove.textContent = 'O‘chirish';
        remove.className = 'danger';
        remove.onclick = async () => {
            if (!confirm(`${dish.name} menyudan o‘chirilsinmi?`)) return;
            remove.disabled = true;
            try {
                await api('/api/dishes/' + dish.id, 'DELETE', {});
                if (editingId === dish.id) resetEditor();
                await load();
                status.textContent = 'Taom o‘chirildi.';
            } catch (error) { status.textContent = error.message; }
            finally { remove.disabled = false; }
        };
        actions.append(edit, remove);
        row.append(image, info, actions);
        list.append(row);
    }
    if (!visible.length) list.textContent = 'Taom topilmadi.';
}

async function load() {
    dishes = await api('/api/dishes');
    await loadCategories();
    render();
}

async function loadCategories() {
    const names = await api('/api/categories');
    const categories = document.querySelector('#category-list');
    categories.replaceChildren();
    for (const category of names) {
        const option = document.createElement('option');
        option.value = category;
        categories.append(option);
    }
    const filters = document.querySelector('#category-filters');
    const options = ['Barchasi', ...names.filter(name => name !== 'Barchasi')];
    if (!options.includes(selectedCategory)) selectedCategory = 'Barchasi';
    filters.replaceChildren(...options.map(name => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = name;
        button.dataset.category = name;
        button.setAttribute('aria-pressed', String(name === selectedCategory));
        return button;
    }));
    render();
}

document.querySelector('#category-filters').onclick = event => {
    const button = event.target.closest('button[data-category]');
    if (!button) return;
    selectedCategory = button.dataset.category;
    document.querySelectorAll('#category-filters button').forEach(item => {
        item.setAttribute('aria-pressed', String(item === button));
    });
    render();
};

const categoryBox = document.querySelector('#category-box');
const categoryName = document.querySelector('#category-name');
const categoryStatus = document.querySelector('#category-status');
function toggleCategory(open) {
    categoryBox.hidden = !open;
    document.querySelector('#add-category').setAttribute('aria-expanded', String(open));
    categoryStatus.textContent = '';
    if (open) categoryName.focus();
}
document.querySelector('#add-category').onclick = () => toggleCategory(categoryBox.hidden);
document.querySelector('#cancel-category').onclick = () => toggleCategory(false);
async function saveCategory() {
    const button = document.querySelector('#save-category');
    if (button.disabled) return;
    const name = categoryName.value.trim();
    if (!name) { categoryStatus.textContent = 'Kategoriya nomini kiriting.'; categoryName.focus(); return; }
    button.disabled = true;
    try {
        const result = await api('/api/categories', 'POST', { name });
        editor.elements.category.value = result.name;
        await loadCategories();
        categoryName.value = '';
        toggleCategory(false);
        status.textContent = 'Kategoriya qo‘shildi.';
    } catch (error) { categoryStatus.textContent = error.message; }
    finally { button.disabled = false; }
}
document.querySelector('#save-category').onclick = saveCategory;
categoryName.onkeydown = event => {
    if (event.key === 'Enter') { event.preventDefault(); saveCategory(); }
};

login.onsubmit = async event => {
    event.preventDefault();
    const button = login.querySelector('button');
    button.disabled = true;
    try {
        const session = await api('/api/login', 'POST', { password: login.elements.password.value });
        login.reset();
        showSession(session.csrf);
        await load();
        status.textContent = '';
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
};
editor.onsubmit = async event => {
    event.preventDefault();
    const button = editor.querySelector('[type=submit]');
    button.disabled = true;
    const data = Object.fromEntries(new FormData(editor));
    const file = editor.elements.photo.files[0];
    delete data.photo;
    data.price = Number(data.price);
    try {
        if (file) {
            status.textContent = 'Rasm yuklanmoqda...';
            const response = await fetch('/api/upload', {
                method: 'POST',
                headers: { 'Content-Type': file.type, 'X-CSRF-Token': csrf || '' },
                body: file,
            });
            const result = await response.json();
            if (!response.ok) {
                if (response.status === 401) showSession(null);
                throw new Error(result.error || 'Rasm yuklanmadi');
            }
            currentImage = result.image;
            editor.elements.photo.value = '';
            editor.elements.photo.required = false;
            preview();
        }
        data.image = currentImage;
        await api('/api/dishes' + (editingId ? '/' + editingId : ''), editingId ? 'PUT' : 'POST', data);
        resetEditor();
        await load();
        status.textContent = 'Saqlandi. Umumiy menyu yangilandi.';
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
};
logout.onclick = async () => {
    try { await api('/api/logout', 'POST', {}); showSession(null); resetEditor(); status.textContent = ''; }
    catch (error) { status.textContent = error.message; }
};
document.querySelector('#search').oninput = render;
document.querySelector('#cancel').onclick = resetEditor;
editor.elements.photo.onchange = preview;
(async () => {
    try { showSession((await api('/api/session')).csrf); if (csrf) await load(); }
    catch (error) { status.textContent = 'Serverga ulanib bo‘lmadi. python server.py orqali saytni ishga tushiring.'; }
})();
