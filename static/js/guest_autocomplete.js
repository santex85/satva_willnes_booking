/**
 * Автодополнение для поля ввода имени гостя
 */
(function() {
    'use strict';

    // URL для API автодополнения
    var AUTocomplete_URL = '/api/v1/guests/autocomplete/';
    
    // Флаг для отладки (можно включить в консоли: window.DEBUG_AUTOCOMPLETE = true)
    var DEBUG_AUTOCOMPLETE = window.DEBUG_AUTOCOMPLETE || false;

    /**
     * Инициализирует автодополнение для поля ввода имени гостя
     * @param {HTMLElement} inputElement - Поле ввода
     * @param {Object} options - Опции конфигурации
     */
    function initGuestAutocomplete(inputElement, options) {
        if (!inputElement) {
            console.error('GuestAutocomplete: inputElement is required');
            return null;
        }
        
        options = options || {};
        var minLength = options.minLength || 2;
        var delay = options.delay || 300;
        var limit = options.limit || 10;
        
        var dropdown = null;
        var selectedIndex = -1;
        var suggestions = [];
        var timeoutId = null;
        var isDropdownVisible = false;
        
        if (DEBUG_AUTOCOMPLETE) {
            console.log('Initializing autocomplete for:', inputElement.id || inputElement.name);
        }

        // Создаем контейнер для dropdown
        function createDropdown() {
            if (dropdown) return dropdown;
            
            dropdown = document.createElement('div');
            dropdown.className = 'guest-autocomplete-dropdown';
            dropdown.style.display = 'none';
            dropdown.style.position = 'absolute';
            dropdown.style.zIndex = '9999'; // Очень высокий z-index для модальных окон
            dropdown.style.backgroundColor = '#fff';
            dropdown.style.border = '1px solid #ccc';
            dropdown.style.borderRadius = '4px';
            dropdown.style.maxHeight = '300px';
            dropdown.style.overflowY = 'auto';
            dropdown.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
            dropdown.style.width = inputElement.offsetWidth + 'px';
            
            document.body.appendChild(dropdown);
            return dropdown;
        }

        // Позиционируем dropdown под полем ввода
        function positionDropdown() {
            if (!dropdown) return;
            
            var rect = inputElement.getBoundingClientRect();
            // Используем getBoundingClientRect для правильного позиционирования относительно viewport
            // Для модальных окон используем fixed позиционирование
            var isInModal = inputElement.closest('.modal');
            
            if (isInModal) {
                // В модальном окне используем fixed позиционирование
                dropdown.style.position = 'fixed';
                dropdown.style.top = (rect.bottom) + 'px';
                dropdown.style.left = rect.left + 'px';
            } else {
                // Обычное позиционирование
                dropdown.style.position = 'absolute';
                dropdown.style.top = (rect.bottom + window.scrollY) + 'px';
                dropdown.style.left = (rect.left + window.scrollX) + 'px';
            }
            
            dropdown.style.width = rect.width + 'px';
            
            // Проверяем, не выходит ли dropdown за пределы экрана
            var dropdownHeight = dropdown.offsetHeight || 200;
            var viewportHeight = window.innerHeight;
            var spaceBelow = viewportHeight - rect.bottom;
            var spaceAbove = rect.top;
            
            // Если места снизу мало, но сверху много - показываем сверху
            if (spaceBelow < dropdownHeight && spaceAbove > spaceBelow) {
                if (isInModal) {
                    dropdown.style.top = (rect.top - dropdownHeight) + 'px';
                } else {
                    dropdown.style.top = (rect.top + window.scrollY - dropdownHeight) + 'px';
                }
            }
        }

        // Загружаем предложения с сервера
        function fetchSuggestions(query) {
            if (query.length < minLength) {
                hideDropdown();
                return;
            }

            var url = AUTocomplete_URL + '?q=' + encodeURIComponent(query) + '&limit=' + limit;
            
            if (DEBUG_AUTOCOMPLETE) {
                console.log('Fetching guest suggestions:', url);
            }
            
            fetch(url)
                .then(function(response) {
                    if (!response.ok) {
                        throw new Error('Network response was not ok: ' + response.status);
                    }
                    return response.json();
                })
                .then(function(data) {
                    suggestions = data || [];
                    if (DEBUG_AUTOCOMPLETE) {
                        console.log('Received suggestions:', suggestions.length, suggestions);
                    }
                    if (suggestions.length > 0) {
                        showSuggestions(suggestions);
                    } else {
                        if (DEBUG_AUTOCOMPLETE) {
                            console.log('No suggestions found for query:', query);
                        }
                        hideDropdown();
                    }
                })
                .catch(function(error) {
                    console.error('Error fetching guest suggestions:', error);
                    hideDropdown();
                });
        }

        // Показываем предложения
        function showSuggestions(items) {
            if (!items || items.length === 0) {
                hideDropdown();
                return;
            }

            createDropdown();
            
            dropdown.innerHTML = '';
            selectedIndex = -1;
            
            items.forEach(function(item, index) {
                var itemElement = document.createElement('div');
                itemElement.className = 'guest-autocomplete-item';
                itemElement.style.padding = '8px 12px';
                itemElement.style.cursor = 'pointer';
                itemElement.style.borderBottom = '1px solid #eee';
                itemElement.dataset.index = index;
                itemElement.dataset.guestId = item.id;
                itemElement.dataset.displayName = item.display_name;
                
                var nameSpan = document.createElement('span');
                nameSpan.textContent = item.display_name;
                nameSpan.style.fontWeight = '500';
                
                var countSpan = document.createElement('span');
                countSpan.textContent = ' (' + item.booking_count + ' бронирований)';
                countSpan.style.color = '#666';
                countSpan.style.fontSize = '0.9em';
                countSpan.style.marginLeft = '8px';
                
                itemElement.appendChild(nameSpan);
                itemElement.appendChild(countSpan);
                
                // Обработчик клика
                itemElement.addEventListener('click', function() {
                    selectGuest(item);
                });
                
                // Обработчик наведения
                itemElement.addEventListener('mouseenter', function() {
                    highlightItem(index);
                });
                
                dropdown.appendChild(itemElement);
            });
            
            // Позиционируем и показываем после добавления элементов
            if (items.length > 0) {
                // Небольшая задержка для правильного расчета размеров
                setTimeout(function() {
                    positionDropdown();
                    dropdown.style.display = 'block';
                    isDropdownVisible = true;
                }, 10);
            } else {
                hideDropdown();
            }
        }

        // Выделяем элемент
        function highlightItem(index) {
            var items = dropdown.querySelectorAll('.guest-autocomplete-item');
            items.forEach(function(item, i) {
                if (i === index) {
                    item.style.backgroundColor = '#f0f0f0';
                } else {
                    item.style.backgroundColor = '';
                }
            });
            selectedIndex = index;
        }

        // Выбираем гостя
        function selectGuest(guest) {
            inputElement.value = guest.display_name;
            inputElement.dataset.guestId = guest.id;
            
            // Триггерим событие изменения
            var event = new Event('change', { bubbles: true });
            inputElement.dispatchEvent(event);
            
            hideDropdown();
        }

        // Скрываем dropdown
        function hideDropdown() {
            if (dropdown) {
                dropdown.style.display = 'none';
            }
            isDropdownVisible = false;
            selectedIndex = -1;
        }

        // Обработчик ввода
        function handleInput() {
            var query = inputElement.value.trim();
            
            // Очищаем таймер
            if (timeoutId) {
                clearTimeout(timeoutId);
            }
            
            // Устанавливаем новый таймер для debounce
            timeoutId = setTimeout(function() {
                if (query.length >= minLength) {
                    fetchSuggestions(query);
                } else {
                    hideDropdown();
                }
            }, delay);
        }

        // Обработчик клавиатуры
        function handleKeyDown(e) {
            if (!isDropdownVisible || !dropdown) return;
            
            var items = dropdown.querySelectorAll('.guest-autocomplete-item');
            if (items.length === 0) return;
            
            switch(e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    selectedIndex = (selectedIndex + 1) % items.length;
                    highlightItem(selectedIndex);
                    items[selectedIndex].scrollIntoView({ block: 'nearest' });
                    break;
                    
                case 'ArrowUp':
                    e.preventDefault();
                    selectedIndex = selectedIndex <= 0 ? items.length - 1 : selectedIndex - 1;
                    highlightItem(selectedIndex);
                    items[selectedIndex].scrollIntoView({ block: 'nearest' });
                    break;
                    
                case 'Enter':
                    e.preventDefault();
                    if (selectedIndex >= 0 && selectedIndex < items.length) {
                        var guestId = items[selectedIndex].dataset.guestId;
                        var displayName = items[selectedIndex].dataset.displayName;
                        selectGuest({ id: guestId, display_name: displayName });
                    }
                    break;
                    
                case 'Escape':
                    e.preventDefault();
                    hideDropdown();
                    break;
            }
        }

        // Обработчик фокуса
        function handleFocus() {
            var query = inputElement.value.trim();
            if (query.length >= minLength) {
                // Небольшая задержка для модальных окон
                setTimeout(function() {
                    fetchSuggestions(query);
                }, 100);
            }
        }

        // Обработчик клика вне поля
        function handleClickOutside(e) {
            if (dropdown && !inputElement.contains(e.target) && !dropdown.contains(e.target)) {
                hideDropdown();
            }
        }

        // Инициализация
        inputElement.addEventListener('input', handleInput);
        inputElement.addEventListener('keydown', handleKeyDown);
        inputElement.addEventListener('focus', handleFocus);
        inputElement.addEventListener('click', function() {
            // При клике тоже показываем предложения, если есть текст
            var query = inputElement.value.trim();
            if (query.length >= minLength) {
                setTimeout(function() {
                    fetchSuggestions(query);
                }, 100);
            }
        });
        document.addEventListener('click', handleClickOutside);
        

        // Очистка при размонтировании (если нужно)
        return {
            destroy: function() {
                inputElement.removeEventListener('input', handleInput);
                inputElement.removeEventListener('keydown', handleKeyDown);
                inputElement.removeEventListener('focus', handleFocus);
                document.removeEventListener('click', handleClickOutside);
                if (dropdown) {
                    dropdown.remove();
                }
            }
        };
    }

    // Автоматическая инициализация для всех полей с data-guest-autocomplete
    function initializeAllAutocompletes() {
        var inputs = document.querySelectorAll('input[data-guest-autocomplete], input#guest_name, input[name="guest_name"]');
        inputs.forEach(function(input) {
            // Пропускаем, если уже инициализировано
            if (input._autocompleteInstance) {
                return;
            }
            // Инициализируем только видимые поля (не в скрытых модальных окнах)
            if (input.offsetParent !== null || input.closest('.modal.show')) {
                input._autocompleteInstance = initGuestAutocomplete(input, {
                    minLength: 2,
                    delay: 300,
                    limit: 10
                });
            }
        });
    }
    
    document.addEventListener('DOMContentLoaded', function() {
        initializeAllAutocompletes();
    });
    
    // Инициализация при открытии модальных окон Bootstrap
    document.addEventListener('shown.bs.modal', function(e) {
        var modal = e.target;
        // Небольшая задержка, чтобы убедиться, что модальное окно полностью отрендерено
        setTimeout(function() {
            var inputs = modal.querySelectorAll('input[data-guest-autocomplete], input#guest_name, input[name="guest_name"]');
            inputs.forEach(function(input) {
                // Удаляем предыдущую инициализацию, если есть
                if (input._autocompleteInstance) {
                    try {
                        input._autocompleteInstance.destroy();
                    } catch (e) {
                        console.warn('Error destroying autocomplete:', e);
                    }
                }
                // Инициализируем заново
                input._autocompleteInstance = initGuestAutocomplete(input, {
                    minLength: 2,
                    delay: 300,
                    limit: 10
                });
            });
        }, 150);
    });
    
    // Экспортируем функцию для ручной инициализации
    window.GuestAutocomplete = {
        init: initGuestAutocomplete,
        initializeAll: initializeAllAutocompletes
    };

})();
