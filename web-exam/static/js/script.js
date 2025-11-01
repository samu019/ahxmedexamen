<!-- Bootstrap JS -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <!-- EasyMDE JS -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/easymde/2.18.0/easymde.min.js"></script>

// Инициализация EasyMDE редакторов
document.addEventListener('DOMContentLoaded', function() {
    // Инициализация EasyMDE для описания книги
    const descriptionTextarea = document.getElementById('short_description');
    if (descriptionTextarea) {
        new EasyMDE({
            element: descriptionTextarea,
            spellChecker: false,
            placeholder: 'Введите краткое описание книги...',
            toolbar: [
                'bold', 'italic', 'heading', '|',
                'quote', 'unordered-list', 'ordered-list', '|',
                'link', 'image', '|',
                'preview', 'side-by-side', 'fullscreen', '|',
                'guide'
            ],
            autosave: {
                enabled: true,
                uniqueId: 'book_description',
                delay: 1000,
            }
        });
    }

    // Инициализация EasyMDE для текста рецензии
    const reviewTextarea = document.getElementById('review_text');
    if (reviewTextarea) {
        new EasyMDE({
            element: reviewTextarea,
            spellChecker: false,
            placeholder: 'Напишите вашу рецензию...',
            toolbar: [
                'bold', 'italic', 'heading', '|',
                'quote', 'unordered-list', 'ordered-list', '|',
                'link', '|',
                'preview', 'side-by-side', 'fullscreen', '|',
                'guide'
            ],
            autosave: {
                enabled: true,
                uniqueId: 'review_text',
                delay: 1000,
            }
        });
    }

    // Анимация появления карточек
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        setTimeout(() => {
            card.style.transition = 'opacity 0.5s ease-out, transform 0.5s ease-out';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
});

// Функция подтверждения удаления
function confirmDelete(itemId, itemTitle, deleteUrl) {
    const modal = document.getElementById('deleteModal');
    const message = document.getElementById('deleteMessage');
    const form = document.getElementById('deleteForm');
    
    message.textContent = `Вы уверены, что хотите удалить "${itemTitle}"?`;
    form.action = deleteUrl;
    
    const deleteModal = new bootstrap.Modal(modal);
    deleteModal.show();
}

// Функция для работы с модальными окнами добавления в подборку
function showAddToCollectionModal(bookId) {
    fetch(`/collections/for-book/${bookId}`)
        .then(response => response.json())
        .then(data => {
            const select = document.getElementById('collectionSelect');
            select.innerHTML = '';
            
            if (data.collections.length === 0) {
                select.innerHTML = '<option value="">Сначала создайте подборку</option>';
                document.getElementById('addToCollectionBtn').disabled = true;
            } else {
                data.collections.forEach(collection => {
                    const option = document.createElement('option');
                    option.value = collection.id;
                    option.textContent = collection.name;
                    select.appendChild(option);
                });
                document.getElementById('addToCollectionBtn').disabled = false;
            }
            
            document.getElementById('addToCollectionForm').dataset.bookId = bookId;
            
            const modal = new bootstrap.Modal(document.getElementById('addToCollectionModal'));
            modal.show();
        })
        .catch(error => {
            console.error('Ошибка:', error);
            alert('Произошла ошибка при загрузке подборок');
        });
}

// Функция добавления книги в подборку
function addToCollection() {
    const form = document.getElementById('addToCollectionForm');
    const bookId = form.dataset.bookId;
    const collectionId = document.getElementById('collectionSelect').value;
    
    if (!collectionId) {
        alert('Выберите подборку');
        return;
    }
    
    fetch(`/collections/${collectionId}/add-book`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ book_id: bookId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const modal = bootstrap.Modal.getInstance(document.getElementById('addToCollectionModal'));
            modal.hide();
            
            // Показать уведомление об успехе
            showNotification('Книга успешно добавлена в подборку!', 'success');
        } else {
            alert(data.message || 'Произошла ошибка');
        }
    })
    .catch(error => {
        console.error('Ошибка:', error);
        alert('Произошла ошибка при добавлении книги в подборку');
    });
}

// Функция показа уведомлений
function showNotification(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.style.position = 'fixed';
    alertDiv.style.top = '20px';
    alertDiv.style.right = '20px';
    alertDiv.style.zIndex = '9999';
    alertDiv.style.minWidth = '300px';
    
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // Автоматическое удаление через 5 секунд
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// Функция для предварительного просмотра загружаемого изображения
function previewImage(input) {
    const preview = document.getElementById('imagePreview');
    const previewContainer = document.getElementById('imagePreviewContainer');
    
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        
        reader.onload = function(e) {
            preview.src = e.target.result;
            previewContainer.style.display = 'block';
        };
        
        reader.readAsDataURL(input.files[0]);
    } else {
        previewContainer.style.display = 'none';
    }
}

// Функция валидации формы
function validateForm(formId) {
    const form = document.getElementById(formId);
    const inputs = form.querySelectorAll('input[required], textarea[required], select[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.classList.add('is-invalid');
            isValid = false;
        } else {
            input.classList.remove('is-invalid');
        }
    });
    
    return isValid;
}

// Функция для экспорта данных в CSV
function exportToCSV(url, filename) {
    fetch(url)
        .then(response => response.blob())
        .then(blob => {
            const link = document.createElement('a');
            link.href = window.URL.createObjectURL(blob);
            link.download = filename;
            link.click();
        })
        .catch(error => {
            console.error('Ошибка при экспорте:', error);
            alert('Произошла ошибка при экспорте данных');
        });
}

// Функция для автоматического изменения размера textarea
function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

// Инициализация подсказок Bootstrap
document.addEventListener('DOMContentLoaded', function() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    const tooltipList = tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

// Функция поиска книг с автодополнением
function setupSearchAutocomplete() {
    const searchInput = document.getElementById('searchTitle');
    if (!searchInput) return;
    
    let timeout;
    searchInput.addEventListener('input', function() {
        clearTimeout(timeout);
        const query = this.value.trim();
        
        if (query.length < 2) {
            hideAutocomplete();
            return;
        }
        
        timeout = setTimeout(() => {
            fetch(`/api/search-suggestions?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    showAutocomplete(data.suggestions, searchInput);
                })
                .catch(error => {
                    console.error('Ошибка автодополнения:', error);
                });
        }, 300);
    });
}

// Показать список автодополнения
function showAutocomplete(suggestions, input) {
    hideAutocomplete();
    
    if (suggestions.length === 0) return;
    
    const dropdown = document.createElement('div');
    dropdown.id = 'autocompleteDropdown';
    dropdown.className = 'autocomplete-dropdown';
    dropdown.style.cssText = `
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: white;
        border: 1px solid #ccc;
        border-top: none;
        border-radius: 0 0 4px 4px;
        max-height: 200px;
        overflow-y: auto;
        z-index: 1000;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    `;
    
    suggestions.forEach(suggestion => {
        const item = document.createElement('div');
        item.className = 'autocomplete-item';
        item.style.cssText = `
            padding: 8px 12px;
            cursor: pointer;
            border-bottom: 1px solid #eee;
        `;
        item.textContent = suggestion;
        
        item.addEventListener('mouseenter', function() {
            this.style.backgroundColor = '#f8f9fa';
        });
        
        item.addEventListener('mouseleave', function() {
            this.style.backgroundColor = 'white';
        });
        
        item.addEventListener('click', function() {
            input.value = suggestion;
            hideAutocomplete();
        });
        
        dropdown.appendChild(item);
    });
    
    input.parentNode.style.position = 'relative';
    input.parentNode.appendChild(dropdown);
}

// Скрыть список автодополнения
function hideAutocomplete() {
    const dropdown = document.getElementById('autocompleteDropdown');
    if (dropdown) {
        dropdown.remove();
    }
}

// Закрыть автодополнение при клике вне его
document.addEventListener('click', function(e) {
    if (!e.target.closest('.autocomplete-dropdown') && 
        !e.target.closest('#searchTitle')) {
        hideAutocomplete();
    }
});

// Функция для работы с рейтингом звездочками
function setupStarRating() {
    const stars = document.querySelectorAll('.rating-star');
    const ratingInput = document.getElementById('rating');
    
    if (!stars.length || !ratingInput) return;
    
    stars.forEach((star, index) => {
        star.addEventListener('mouseenter', function() {
            highlightStars(index + 1);
        });
        
        star.addEventListener('click', function() {
            const rating = index + 1;
            ratingInput.value = rating;
            setRating(rating);
        });
    });
    
    // Восстановить рейтинг при уходе мыши
    const ratingContainer = document.querySelector('.star-rating');
    if (ratingContainer) {
        ratingContainer.addEventListener('mouseleave', function() {
            setRating(ratingInput.value || 0);
        });
    }
}

function highlightStars(rating) {
    const stars = document.querySelectorAll('.rating-star');
    stars.forEach((star, index) => {
        if (index < rating) {
            star.classList.remove('far');
            star.classList.add('fas');
            star.style.color = '#ffc107';
        } else {
            star.classList.remove('fas');
            star.classList.add('far');
            star.style.color = '#dee2e6';
        }
    });
}

function setRating(rating) {
    highlightStars(rating);
}

// Функция для динамической загрузки контента
function loadContent(url, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    // Показать индикатор загрузки
    container.innerHTML = '<div class="text-center py-4"><i class="fas fa-spinner fa-spin"></i> Загрузка...</div>';
    
    fetch(url)
        .then(response => response.text())
        .then(html => {
            container.innerHTML = html;
            // Переинициализировать компоненты Bootstrap
            initializeBootstrapComponents(container);
        })
        .catch(error => {
            console.error('Ошибка загрузки:', error);
            container.innerHTML = '<div class="alert alert-danger">Ошибка загрузки данных</div>';
        });
}

// Переинициализация компонентов Bootstrap
function initializeBootstrapComponents(container) {
    // Переинициализировать подсказки
    const tooltips = container.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(el => new bootstrap.Tooltip(el));
    
    // Переинициализировать модальные окна
    const modals = container.querySelectorAll('.modal');
    modals.forEach(el => new bootstrap.Modal(el));
}

// Функция для обработки форм через AJAX
function submitFormAjax(formId, successCallback) {
    const form = document.getElementById(formId);
    if (!form) return;
    
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const formData = new FormData(form);
        const submitBtn = form.querySelector('button[type="submit"]');
        
        // Заблокировать кнопку отправки
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Отправка...';
        }
        
        fetch(form.action, {
            method: form.method,
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (successCallback) {
                    successCallback(data);
                } else {
                    showNotification(data.message || 'Операция выполнена успешно', 'success');
                }
            } else {
                showNotification(data.message || 'Произошла ошибка', 'danger');
            }
        })
        .catch(error => {
            console.error('Ошибка:', error);
            showNotification('Произошла ошибка при отправке формы', 'danger');
        })
        .finally(() => {
            // Разблокировать кнопку отправки
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = submitBtn.dataset.originalText || 'Отправить';
            }
        });
    });
}

// Инициализация всех компонентов при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    setupSearchAutocomplete();
    setupStarRating();
    
    // Сохранить оригинальный текст кнопок отправки
    const submitButtons = document.querySelectorAll('button[type="submit"]');
    submitButtons.forEach(btn => {
        btn.dataset.originalText = btn.innerHTML;
    });
    
    // Автоматический ресайз для всех textarea
    const textareas = document.querySelectorAll('textarea');
    textareas.forEach(textarea => {
        textarea.addEventListener('input', function() {
            autoResize(this);
        });
        // Инициальный ресайз
        autoResize(textarea);
    });
});

// Функция для работы с фильтрами поиска
function toggleSearchFilters() {
    const filtersContainer = document.getElementById('searchFilters');
    const toggleBtn = document.getElementById('toggleFiltersBtn');
    
    if (filtersContainer.style.display === 'none' || !filtersContainer.style.display) {
        filtersContainer.style.display = 'block';
        toggleBtn.innerHTML = '<i class="fas fa-chevron-up"></i> Скрыть фильтры';
    } else {
        filtersContainer.style.display = 'none';
        toggleBtn.innerHTML = '<i class="fas fa-chevron-down"></i> Показать фильтры';
    }
}

// Функция для сброса фильтров поиска
function resetSearchFilters() {
    const form = document.getElementById('searchForm');
    if (form) {
        form.reset();
        // Обновить select элементы
        const selects = form.querySelectorAll('select');
        selects.forEach(select => {
            select.selectedIndex = 0;
        });
    }
}