/**
 * Future Sections Settings JavaScript
 *
 * Initializes flatpickr multi-date picker for pending notification dates
 * and the visual teaching form configuration UI.
 */

function initPendingNotificationDatesPicker() {
    var $picker = $('.pending-notification-dates-picker');
    if ($picker.length && !$picker.data('flatpickr-initialized')) {
        var $startDate = $('input[name="starting_date"]');
        var $endDate = $('input[name="ending_date"]');

        var minDate = $startDate.val() || null;
        var maxDate = $endDate.val() || null;

        $picker.flatpickr({
            mode: 'multiple',
            dateFormat: 'm/d/Y',
            minDate: minDate,
            maxDate: maxDate,
            conjunction: ', ',
            allowInput: false,
            clickOpens: true,
            onChange: function(selectedDates, dateStr, instance) {
                // Sort dates chronologically
                selectedDates.sort(function(a, b) { return a - b; });
                var formatted = selectedDates.map(function(d) {
                    return instance.formatDate(d, 'm/d/Y');
                }).join(', ');
                $picker.val(formatted);
            }
        });
        $picker.data('flatpickr-initialized', true);

        // Update date constraints when start/end dates change
        $startDate.on('change', function() {
            var fp = $picker[0]._flatpickr;
            if (fp) fp.set('minDate', $(this).val());
        });
        $endDate.on('change', function() {
            var fp = $picker[0]._flatpickr;
            if (fp) fp.set('maxDate', $(this).val());
        });
    }
}

function initReviewedNotificationToggle() {
    var $toggle = $('select[name="send_reviewed_notification"]');
    if (!$toggle.length) return;

    var $subject = $('select[name="send_reviewed_notification"]')
        .closest('form')
        .find('input[name="reviewed_email_subject"]')
        .closest('.form-group');
    var $message = $('select[name="send_reviewed_notification"]')
        .closest('form')
        .find('textarea[name="reviewed_email_message"]')
        .closest('.form-group');

    function toggleFields() {
        var show = $toggle.val() === '1';
        $subject.toggle(show);
        $message.toggle(show);
    }

    toggleFields();
    $toggle.on('change', toggleFields);
}

/**
 * Reorder a config table's draggable rows to match saved weights.
 *
 * Rows render in schema declaration order; without this a saved order does
 * not survive a page reload. Unweighted rows sort last, and ties keep their
 * current DOM order.
 */
function applySavedFieldOrder($ui, weights, inputClass) {
    var $table = $ui.find('table').first();
    var $body = $table.find('tbody').first();
    if (!$body.length) return;

    var rows = [];
    $body.children('tr').each(function (index) {
        var $row = $(this);
        var $input = $row.find('.' + inputClass);
        rows.push({
            el: this,
            draggable: $row.find('.fw-grip').length > 0,
            index: index,
            weight: $input.length && weights.hasOwnProperty($input.data('field'))
                ? weights[$input.data('field')]
                : Number.MAX_SAFE_INTEGER
        });
    });

    rows.filter(function (r) { return r.draggable; })
        .sort(function (a, b) {
            if (a.weight !== b.weight) return a.weight - b.weight;
            return a.index - b.index;
        })
        .forEach(function (r) { $body.append(r.el); });
}

function initTeachingFormConfig() {
    var $hidden = $('input[name="teaching_form_config"]');
    if (!$hidden.length) return;
    var $ui = $('#teaching-form-config-ui');
    if (!$ui.length) return;

    // Don't re-initialize
    if ($ui.data('tfc-initialized')) return;
    $ui.data('tfc-initialized', true);

    // Parse existing config
    var config = {};
    try {
        config = JSON.parse($hidden.val() || '{}');
    } catch (e) {
        config = {};
    }

    var fields = config.fields || [];
    var required = config.required || [];
    var labels = config.labels || {};
    var weights = config.weights || {};
    var showSyllabus = config.show_syllabus !== undefined ? config.show_syllabus : false;
    var displayTemplate = config.display_template || '';

    // Populate UI from config
    $ui.find('.tfc-visible').each(function () {
        $(this).prop('checked', fields.indexOf($(this).data('field')) !== -1);
    });

    $ui.find('.tfc-required').each(function () {
        $(this).prop('checked', required.indexOf($(this).data('field')) !== -1);
    });

    $ui.find('.tfc-label').each(function () {
        var label = labels[$(this).data('field')];
        if (label) $(this).val(label);
    });

    $ui.find('.tfc-weight').each(function () {
        var w = weights[$(this).data('field')];
        if (w !== undefined) $(this).val(w);
    });

    applySavedFieldOrder($ui, weights, 'tfc-weight');

    $('#tfc-show-syllabus').prop('checked', showSyllabus);
    $('#tfc-display-template').val(displayTemplate);

    // Sync UI state to hidden JSON field
    function syncToHidden() {
        var visibleFields = [];
        $ui.find('.tfc-visible:checked').each(function () {
            visibleFields.push($(this).data('field'));
        });

        var newRequired = ['term'];
        $ui.find('.tfc-required:checked').each(function () {
            newRequired.push($(this).data('field'));
        });

        var newLabels = {};
        $ui.find('.tfc-label').each(function () {
            var val = $(this).val().trim();
            if (val) newLabels[$(this).data('field')] = val;
        });

        var newWeights = {};
        $ui.find('.tfc-weight').each(function () {
            var val = $(this).val();
            if (val !== '' && val !== undefined) {
                newWeights[$(this).data('field')] = parseInt(val, 10);
            }
        });

        // Sort visible fields by weight (lighter first, unweighted last)
        visibleFields.sort(function (a, b) {
            var wa = newWeights.hasOwnProperty(a) ? newWeights[a] : Number.MAX_SAFE_INTEGER;
            var wb = newWeights.hasOwnProperty(b) ? newWeights[b] : Number.MAX_SAFE_INTEGER;
            return wa - wb;
        });

        var newFields = ['term'].concat(visibleFields);

        var newConfig = {
            fields: newFields,
            required: newRequired,
            show_syllabus: $('#tfc-show-syllabus').is(':checked')
        };

        if (Object.keys(newLabels).length > 0) newConfig.labels = newLabels;
        if (Object.keys(newWeights).length > 0) newConfig.weights = newWeights;

        // Preserve help_texts from original config (not exposed in UI)
        if (config.help_texts && Object.keys(config.help_texts).length > 0) {
            newConfig.help_texts = config.help_texts;
        }

        var template = $('#tfc-display-template').val().trim();
        if (template) newConfig.display_template = template;

        $hidden.val(JSON.stringify(newConfig));
    }

    // Auto-check visible when required is checked
    $ui.on('change', '.tfc-required', function () {
        if ($(this).is(':checked')) {
            $ui.find('.tfc-visible[data-field="' + $(this).data('field') + '"]')
                .prop('checked', true);
        }
        syncToHidden();
    });

    // Auto-uncheck required when visible is unchecked
    $ui.on('change', '.tfc-visible', function () {
        if (!$(this).is(':checked')) {
            $ui.find('.tfc-required[data-field="' + $(this).data('field') + '"]')
                .prop('checked', false);
        }
        syncToHidden();
    });

    $ui.on('change', '#tfc-show-syllabus', syncToHidden);
    $ui.on('input', '.tfc-label, .tfc-weight, #tfc-display-template', syncToHidden);

    // field_weights.js renumbers weight inputs on drop by assigning
    // input.value directly (no 'input' event), so re-serialize after a drag
    // settles. dragend fires after its document-level drop handler has
    // already renumbered; the setTimeout guarantees ordering regardless.
    $ui.on('dragend drop', function () { setTimeout(syncToHidden, 0); });

    // Sync on form submit
    $hidden.closest('form').on('submit', syncToHidden);
}

function initAddTeacherFormConfig() {
    var $hidden = $('input[name="add_teacher_form_config"]');
    if (!$hidden.length) return;
    var $ui = $('#add-teacher-form-config-ui');
    if (!$ui.length) return;

    // Don't re-initialize
    if ($ui.data('atfc-initialized')) return;
    $ui.data('atfc-initialized', true);

    // Parse existing config
    var config = {};
    try {
        config = JSON.parse($hidden.val() || '{}');
    } catch (e) {
        config = {};
    }

    var fields = config.fields || [];
    var required = config.required || [];
    var labels = config.labels || {};
    var weights = config.weights || {};

    // Populate UI from config
    $ui.find('.atfc-visible').each(function () {
        $(this).prop('checked', fields.indexOf($(this).data('field')) !== -1);
    });

    $ui.find('.atfc-required').each(function () {
        $(this).prop('checked', required.indexOf($(this).data('field')) !== -1);
    });

    $ui.find('.atfc-label').each(function () {
        var label = labels[$(this).data('field')];
        if (label) $(this).val(label);
    });

    $ui.find('.atfc-weight').each(function () {
        var w = weights[$(this).data('field')];
        if (w !== undefined) $(this).val(w);
    });

    applySavedFieldOrder($ui, weights, 'atfc-weight');

    // Sync UI state to hidden JSON field
    function syncToHidden() {
        var alwaysIncluded = ['highschool', 'course', 'term', 'teacher'];

        var visibleFields = [];
        $ui.find('.atfc-visible:checked').each(function () {
            visibleFields.push($(this).data('field'));
        });

        var newRequired = alwaysIncluded.slice();
        $ui.find('.atfc-required:checked').each(function () {
            newRequired.push($(this).data('field'));
        });

        var newLabels = {};
        $ui.find('.atfc-label').each(function () {
            var val = $(this).val().trim();
            if (val) newLabels[$(this).data('field')] = val;
        });

        var newWeights = {};
        $ui.find('.atfc-weight').each(function () {
            var val = $(this).val();
            if (val !== '' && val !== undefined) {
                newWeights[$(this).data('field')] = parseInt(val, 10);
            }
        });

        // Sort visible fields by weight (lighter first, unweighted last)
        visibleFields.sort(function (a, b) {
            var wa = newWeights.hasOwnProperty(a) ? newWeights[a] : Number.MAX_SAFE_INTEGER;
            var wb = newWeights.hasOwnProperty(b) ? newWeights[b] : Number.MAX_SAFE_INTEGER;
            return wa - wb;
        });

        var newFields = alwaysIncluded.concat(visibleFields);

        var newConfig = {
            fields: newFields,
            required: newRequired
        };

        if (Object.keys(newLabels).length > 0) newConfig.labels = newLabels;
        if (Object.keys(newWeights).length > 0) newConfig.weights = newWeights;

        // Preserve help_texts from original config (not exposed in UI)
        if (config.help_texts && Object.keys(config.help_texts).length > 0) {
            newConfig.help_texts = config.help_texts;
        }

        $hidden.val(JSON.stringify(newConfig));
    }

    // Auto-check visible when required is checked
    $ui.on('change', '.atfc-required', function () {
        if ($(this).is(':checked')) {
            $ui.find('.atfc-visible[data-field="' + $(this).data('field') + '"]')
                .prop('checked', true);
        }
        syncToHidden();
    });

    // Auto-uncheck required when visible is unchecked
    $ui.on('change', '.atfc-visible', function () {
        if (!$(this).is(':checked')) {
            $ui.find('.atfc-required[data-field="' + $(this).data('field') + '"]')
                .prop('checked', false);
        }
        syncToHidden();
    });

    $ui.on('input', '.atfc-label, .atfc-weight', syncToHidden);

    // field_weights.js renumbers weight inputs on drop by assigning
    // input.value directly (no 'input' event), so re-serialize after a drag
    // settles. dragend fires after its document-level drop handler has
    // already renumbered; the setTimeout guarantees ordering regardless.
    $ui.on('dragend drop', function () { setTimeout(syncToHidden, 0); });

    // Sync on form submit
    $hidden.closest('form').on('submit', syncToHidden);
}

function initNewTeacherToggle() {
    var $toggle = $('select[name="allow_new_teacher_create"]');
    if (!$toggle.length) return;

    var $form = $toggle.closest('form');
    var $label = $form.find('input[name="new_teacher_create_label"]')
        .closest('.form-group');
    var $appFor = $form.find('input[name="create_new_instructor_app"]')
        .first()
        .closest('.form-group');
    var $defaultStatus = $form.find('select[name="default_instructor_app_status"]')
        .closest('.form-group');

    function toggleFields() {
        var show = $toggle.val() === '1';
        $label.toggle(show);
    }

    toggleFields();
    $toggle.on('change', toggleFields);
}

function initPersonnelConfirmationToggle() {
    var $toggle = $('select[name="require_personnel_confirmation"]');
    if (!$toggle.length) return;

    var $form = $toggle.closest('form');
    var $roles = $form.find('input[name="school_admin_roles"]')
        .first()
        .closest('.form-group');
    var $confirmPersonnel = $form.find('textarea[name="confirm_new_personnel"]')
        .closest('.form-group');
    var $requireAllRoles = $form.find('select[name="require_all_roles_confirmed"]')
        .closest('.form-group');

    function toggleFields() {
        var show = $toggle.val() === '1';
        $roles.toggle(show);
        $confirmPersonnel.toggle(show);
        $requireAllRoles.toggle(show);
    }

    toggleFields();
    $toggle.on('change', toggleFields);
}

var _termMappingInitialized = false;
function initTermMapping() {
    if (_termMappingInitialized) return;

    var $academicYear = $('#id_academic_year');
    var $prevAcademicYear = $('#id_previous_academic_year');
    var $hidden = $('#id_term_mapping');
    var $ui = $('#term-mapping-ui');
    var $tbody = $('#term-mapping-table tbody');

    if (!$academicYear.length || !$prevAcademicYear.length || !$hidden.length) return;
    _termMappingInitialized = true;

    var savedMapping = {};
    try { savedMapping = JSON.parse($hidden.val() || '{}'); } catch (e) { savedMapping = {}; }

    function fetchTerms(academicYearId) {
        if (!academicYearId) return $.Deferred().resolve([]).promise();
        return $.getJSON('/ce/api/term/', { academic_year: academicYearId, format: 'json' });
    }

    function buildMappingUI() {
        var prevId = $prevAcademicYear.val();
        var reqId = $academicYear.val();

        if (!prevId || !reqId) {
            $ui.hide();
            return;
        }

        $.when(fetchTerms(prevId), fetchTerms(reqId)).done(function(prevResp, reqResp) {
            var prevTerms = (prevResp[0] && prevResp[0].results) ? prevResp[0].results : (Array.isArray(prevResp[0]) ? prevResp[0] : []);
            var reqTerms = (reqResp[0] && reqResp[0].results) ? reqResp[0].results : (Array.isArray(reqResp[0]) ? reqResp[0] : []);

            $tbody.empty();

            if (prevTerms.length === 0) {
                $tbody.append('<tr><td colspan="2" class="text-muted">No terms found for previous year</td></tr>');
                $ui.show();
                return;
            }

            // Build options for requesting year terms
            var reqOptions = '<option value="">-- Select --</option>';
            $.each(reqTerms, function(_, term) {
                reqOptions += '<option value="' + term.id + '">' + term.label + '</option>';
            });

            $.each(prevTerms, function(_, prevTerm) {
                var selected = savedMapping[prevTerm.id] || '';
                var $row = $('<tr>' +
                    '<td>' + prevTerm.label + '</td>' +
                    '<td><select class="form-control term-map-select" data-prev-term="' + prevTerm.id + '">' + reqOptions + '</select></td>' +
                    '</tr>');

                if (selected) {
                    $row.find('select').val(selected);
                }

                $tbody.append($row);
            });

            $ui.show();
        });
    }

    function syncToHidden() {
        var mapping = {};
        $tbody.find('.term-map-select').each(function() {
            var prevTermId = $(this).data('prev-term');
            var reqTermId = $(this).val();
            if (reqTermId) {
                mapping[prevTermId] = reqTermId;
            }
        });
        $hidden.val(JSON.stringify(mapping));
    }

    $(document).on('change', '.term-map-select', syncToHidden);
    $academicYear.on('change', function() { savedMapping = {}; buildMappingUI(); });
    $prevAcademicYear.on('change', function() { savedMapping = {}; buildMappingUI(); });

    buildMappingUI();
}

function initReviewToggles() {
    var $require = $('select[name="require_review"]');
    var $assign = $('select[name="assign_mentor"]');
    if (!$require.length && !$assign.length) return;

    var $form = $require.length ? $require.closest('form') : $assign.closest('form');
    var $reviewerRoles = $form.find('input[name="reviewer_roles"]')
        .first()
        .closest('.form-group');
    var $assignMentor = $assign.closest('.form-group');
    var $mentorRole = $form.find('select[name="mentor_default_role"]')
        .closest('.form-group');

    function sync() {
        var reviewOn = $require.val() === '1';
        $reviewerRoles.toggle(reviewOn);
        $assignMentor.toggle(reviewOn);
        // Mentor role only visible when both review is on AND assign_mentor is Yes.
        $mentorRole.toggle(reviewOn && $assign.val() === '1');
    }
    sync();
    $require.on('change', sync);
    $assign.on('change', sync);
}

function initTermFieldScrollContainer(fieldName) {
    // Wrap a CheckboxSelectMultiple's <ul> in a scrollable div so long term
    // lists don't push the rest of the settings form off-screen.
    var $first = $('input[name="' + fieldName + '"]').first();
    if (!$first.length) return;
    var $list = $first.closest('ul');
    if (!$list.length || $list.parent().hasClass('term-scroll')) return;
    $list.wrap(
        '<div class="term-scroll" style="' +
        'max-height: 280px; overflow-y: auto; ' +
        'border: 1px solid #dee2e6; border-radius: .25rem; ' +
        'padding: .5rem .75rem; background: #fafafa;"></div>'
    );
}

// ── AY-scoped term checkboxes ───────────────────────────────────────────
// Cycle Terms follow the "Requesting Information For" AY (#id_academic_year);
// Lookback Terms follow the "Previous Year Reference" AY
// (#id_previous_academic_year). When an AY changes, refetch that year's terms
// and rebuild the matching checkbox list, preserving still-valid checked terms.
var AY_TERM_PAIRS = [
    { aySelector: '#id_academic_year',          termName: 'cycle_terms' },
    { aySelector: '#id_previous_academic_year', termName: 'lookback_terms' }
];

function rebuildTermCheckboxes(termName, academicYearId) {
    var $group = $('#div_id_' + termName);
    if (!$group.length) {
        var $existing = $('input[name="' + termName + '"]').first();
        if ($existing.length) $group = $existing.closest('.form-group');
    }
    if (!$group.length) return;

    // Preserve currently-checked term ids across the rebuild.
    var checked = {};
    $('input[name="' + termName + '"]:checked').each(function () {
        checked[$(this).val()] = true;
    });

    function render(terms) {
        var items = '';
        $.each(terms, function (i, term) {
            var fieldId = 'id_' + termName + '_' + i;
            var isChecked = checked[term.id] ? ' checked' : '';
            items +=
                '<li><label for="' + fieldId + '">' +
                '<input type="checkbox" name="' + termName + '" value="' +
                term.id + '" id="' + fieldId + '"' + isChecked + '> ' +
                term.label + '</label></li>';
        });

        var $list = $group.find('ul').first();
        if (!$list.length) {
            // Empty server render had no <ul>; create one after the field label.
            $list = $('<ul></ul>');
            var $label = $group.find('label').first();
            if ($label.length) { $label.after($list); } else { $group.append($list); }
        }
        $list.html(items);

        // Re-apply the scroll wrapper (no-op if already wrapped) and refresh
        // the cycle-terms AY hint via the delegated handler.
        initTermFieldScrollContainer(termName);
        $('input[name="' + termName + '"]').first().trigger('change');
    }

    if (!academicYearId) { render([]); return; }

    $.getJSON('/ce/api/term/', { academic_year: academicYearId, format: 'json' })
        .done(function (resp) {
            var terms = (resp && resp.results) ? resp.results
                       : (Array.isArray(resp) ? resp : []);
            render(terms);
        });
}

var _ayScopedTermsInitialized = false;
function initAyScopedTerms() {
    if (_ayScopedTermsInitialized) return;
    var bound = false;
    AY_TERM_PAIRS.forEach(function (pair) {
        var $ay = $(pair.aySelector);
        if (!$ay.length) return;
        bound = true;
        $ay.on('change', function () {
            rebuildTermCheckboxes(pair.termName, $ay.val());
        });
    });
    if (bound) { _ayScopedTermsInitialized = true; }
}

function initCycleTermsHint() {
    initTermFieldScrollContainer('cycle_terms');
    initTermFieldScrollContainer('lookback_terms');

    function refreshHint() {
        var $group = $('#div_id_cycle_terms');
        if (!$group.length) {
            var $first = $('input[name="cycle_terms"]').first();
            if ($first.length) $group = $first.closest('.form-group');
        }
        if (!$group.length) return;

        var ays = new Set();
        $('input[name="cycle_terms"]:checked').each(function () {
            var label = $(this).siblings('label').text().trim()
                     || $(this).closest('label').text().trim();
            var m = label.match(/(\d{4})/);
            if (m) ays.add(m[1]);
        });

        var $note = $group.find('#cycle-terms-ay-note');
        if ($note.length === 0) {
            $note = $('<small id="cycle-terms-ay-note" class="form-text text-muted"></small>');
            $group.append($note);
        }
        if (ays.size > 1) {
            $note.text('Warning: selected terms appear to span multiple academic years; saving will fail.')
                 .removeClass('text-muted').addClass('text-danger');
        } else {
            $note.text('').removeClass('text-danger').addClass('text-muted');
        }
    }

    refreshHint();
    $(document).off('change.cycleHint')
               .on('change.cycleHint', 'input[name="cycle_terms"]', refreshHint);
}

function initAll() {
    var inits = [
        initTeachingFormConfig,
        initAddTeacherFormConfig,
        initReviewedNotificationToggle,
        initPersonnelConfirmationToggle,
        initReviewToggles,
        initCycleTermsHint,
        initAyScopedTerms,
        initNewTeacherToggle,
        initPendingNotificationDatesPicker,
        initTermMapping,
    ];
    for (var i = 0; i < inits.length; i++) {
        try { inits[i](); } catch (e) {
            console.warn('Settings init error (' + inits[i].name + '):', e.message);
        }
    }
}

// Initialize on AJAX complete (for settings forms loaded dynamically)
$(document).ajaxComplete(initAll);

// Initialize on document ready
$(document).ready(initAll);
