/**
 * Generic drag-and-drop row reordering for settings field-config tables.
 *
 * Rows carrying a `.fw-grip` cell become draggable. On drop, every weight
 * input in the table is renumbered from 0 in DOM order and an `input` event
 * is fired so the table's existing serializer picks up the new order.
 *
 * Rows without a `.fw-grip` cell ("Always included" rows) are not draggable
 * and are not renumbered; they are pinned at the top of the table by the
 * serializer regardless of position.
 */
(function (window, document) {
    'use strict';

    function rowsOf(table) {
        return Array.prototype.slice.call(
            table.querySelectorAll('tbody > tr'));
    }

    function isDraggable(row) {
        return !!(row && row.querySelector('.fw-grip'));
    }

    function tableOf(row) {
        return row ? row.closest('table') : null;
    }

    function renumber(table, weightInputClass) {
        var order = 0;
        rowsOf(table).forEach(function (row) {
            if (!isDraggable(row)) {
                return;
            }
            var input = row.querySelector('.' + weightInputClass);
            if (!input) {
                return;
            }
            input.value = order;
            order += 1;
            input.dispatchEvent(new Event('input', {bubbles: true}));
        });
    }

    function initFieldReorder(tableSelector, weightInputClass) {
        var container = document.querySelector(tableSelector);
        if (!container) {
            return;
        }
        var table = container.querySelector('table');
        if (!table || table.getAttribute('data-reorder-bound') === '1') {
            return;
        }
        table.setAttribute('data-reorder-bound', '1');

        var dragging = null;

        rowsOf(table).forEach(function (row) {
            if (isDraggable(row)) {
                row.setAttribute('draggable', 'true');
            }
        });

        table.addEventListener('dragstart', function (event) {
            var row = event.target.closest('tr');
            if (!isDraggable(row)) {
                return;
            }
            dragging = row;
            row.classList.add('fw-dragging');
            // Firefox requires data to be set for the drag to start.
            event.dataTransfer.setData('text/plain', '');
            event.dataTransfer.effectAllowed = 'move';
        });

        table.addEventListener('dragover', function (event) {
            if (!dragging) {
                return;
            }
            var row = event.target.closest('tr');
            // Only reorder within the table the drag started in, and never
            // past a pinned "Always included" row.
            if (!row || !isDraggable(row) || tableOf(row) !== tableOf(dragging)) {
                return;
            }
            event.preventDefault();
            if (row === dragging) {
                return;
            }
            var rows = rowsOf(table);
            var before = rows.indexOf(row) < rows.indexOf(dragging);
            row.parentNode.insertBefore(
                dragging, before ? row : row.nextSibling);
        });

        table.addEventListener('drop', function (event) {
            if (dragging) {
                event.preventDefault();
            }
        });

        table.addEventListener('dragend', function () {
            if (!dragging) {
                return;
            }
            dragging.classList.remove('fw-dragging');
            dragging = null;
            renumber(table, weightInputClass);
        });
    }

    window.initFieldReorder = initFieldReorder;
})(window, document);
