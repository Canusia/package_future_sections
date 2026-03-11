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
        $appFor.toggle(show);
        $defaultStatus.toggle(show);
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

function initAll() {
    var inits = [
        initTeachingFormConfig,
        initAddTeacherFormConfig,
        initReviewedNotificationToggle,
        initPersonnelConfirmationToggle,
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
