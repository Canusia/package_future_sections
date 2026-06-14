# Future Sections — Scope Cycle/Lookback Terms to Selected Academic Years Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the future_sections settings form, ask the two academic-year selectors *first*, then scope each term checkbox list to its academic year — **Cycle Terms** show only the "Requesting Information For" year's terms, **Lookback Terms** only the "Previous Year Reference" year's terms — so the lists stop growing unbounded.

**Architecture:** The settings form (`settings/future_sections.py`, class `future_sections`) renders all `Term` rows as `CheckboxSelectMultiple` lists today, which gets long. We (1) reorder field declarations so `academic_year` + `previous_academic_year` precede `cycle_terms` + `lookback_terms`; (2) in `__init__`, scope the term querysets to the saved AYs on **unbound** (render) forms while keeping the **full** queryset on **bound** (POST) forms so field-level validation still passes (the existing `clean_cycle_terms`/`clean_lookback_terms` already enforce the real rules); (3) add JS that re-fetches a year's terms from the existing `/ce/api/term/?academic_year=<id>` endpoint and rebuilds the relevant checkbox list whenever an AY dropdown changes, preserving still-valid checked terms.

**Tech Stack:** Django 5.2 forms (`ModelMultipleChoiceField` + `CheckboxSelectMultiple`), crispy-forms layout, the `setting` app (`from_db()`/`run_record()` lifecycle, key `cis_future_sections`), jQuery in `staticfiles/future_sections/js/settings.js`, DRF `TermViewSet` at `/ce/api/term/`.

---

## Context the engineer needs

- **Repo:** This is the `future_sections` editable submodule — its own git repo at `/repos/ewu/webapp/future_sections` (currently on branch `main`). App code lives in the **inner** package `future_sections/future_sections/`. Installed as `future_sections.future_sections` (DevFutureSectionsConfig), so the test label prefix is `future_sections.future_sections.tests.…`.
- **Run all commands in the tenant container** against the live mount:
  ```
  docker exec -w /app/webapp django_web_ewu python manage.py <cmd>
  ```
  (Never run host `python`; `/app/webapp` is the live mount, `/var/webapp` is a stale build copy.)
- **No model migration, no packaging change.** This edits only existing `.py`/`.js` files inside `future_sections/future_sections/` and adds one test module. `makemigrations future_sections` must report "No changes detected" (verified in Task 4). The `submod-migration-deps` and `submod-package-manifest` skills do **not** apply.

### How the settings form loads and saves (already verified — do not re-implement)

- **Render:** `setting` app's `record_details` view does `initial = report_class.from_db(); form = report_class(request, initial=initial)`. So in `__init__` (after `super().__init__`), `self.initial` is the saved config dict: `academic_year` and `previous_academic_year` are **string UUIDs**, `cycle_terms`/`lookback_terms` are **lists of string UUIDs**. (`future_sections.future_sections.settings.future_sections.future_sections.from_db` returns `Setting.objects.get(key='cis_future_sections').value`.)
- **Save:** `run_record` view does `form = report_class(request, request.POST); form.is_valid()` → `form.run_record()`. So the POST path is a **bound** form with **empty `self.initial`**.
- **Field-level validation gotcha (this is why the bound/unbound split matters):** Django's `_clean_fields` runs `field.clean(value)` **before** `clean_<fieldname>`. For `ModelMultipleChoiceField`, `field.clean()` rejects any submitted id **not in `self.fields['cycle_terms'].queryset`**. The current code sidesteps this by setting the queryset to **all** terms in `__init__`. The custom `clean_cycle_terms`/`clean_lookback_terms` (which do `Term.objects.filter(id__in=self.data.getlist(...))`) and `clean()` (single-AY enforcement) are what actually validate. **Therefore: on a bound form we must keep the full term queryset**, or every save fails with "not a valid choice". We only scope the queryset on unbound (render) forms — which is exactly where "show fewer terms" matters.
- **AY is also derived from cycle_terms on save:** `_to_python()` calls `_derive_academic_year_from_cycle_terms()` and overwrites `result['academic_year']`. With this change the user picks the AY first and cycle_terms are scoped to it, so the derived value equals the selected value — behavior stays consistent. Leave `_to_python` untouched.

### The dynamic-terms endpoint (already exists, already used here)

- `GET /ce/api/term/?academic_year=<uuid>&format=json` → `cis.views.term.TermViewSet` (ReadOnly), filters `Term.objects.filter(academic_year__id=...)`, serialized by `TermSerializer` which always includes `id` and `label` (e.g. `"Fall 2026"`).
- `settings.js`'s existing `initTermMapping()` already calls this exact endpoint via `$.getJSON('/ce/api/term/', { academic_year: id, format: 'json' })` and handles both `resp.results` (paginated) and a bare array. Mirror that response handling.

### Current field declaration order (the part we are reordering)

In `settings/future_sections.py` the relevant fields are declared in this order today (≈lines 83–123):
`cycle_terms` → `lookback_terms` → `academic_year` → `previous_academic_year` → `term_mapping`.
The crispy layout is built by iterating `list(self.fields.keys())` in declaration order (≈lines 781–794), so **changing declaration order changes on-screen order**. Target order:
`academic_year` → `previous_academic_year` → `cycle_terms` → `lookback_terms` → `term_mapping`.

### Existing tests to mirror / not break

- `future_sections/future_sections/tests/test_cycle_terms_settings.py` — bound-form validation tests (required, must-share-AY, AY-derivation). These instantiate `FSForm(request, data=...)` (bound) and must keep passing. They rely on the **full** queryset on bound forms, which Task 2 preserves.

---

## File Structure

All paths are inside the inner package `future_sections/future_sections/`.

- **Modify:** `settings/future_sections.py`
  - Move the `academic_year` and `previous_academic_year` field declarations to **above** `cycle_terms` (Task 1); add a sentence to the two term fields' `help_text` describing the tie (Task 1).
  - In `__init__`, replace the unconditional term-queryset block with a bound/unbound split that scopes to the saved AYs on render (Task 2).
- **Modify:** `staticfiles/future_sections/js/settings.js`
  - Add `initAyScopedTerms()` + `rebuildTermCheckboxes()`, register in `initAll()`, and make the cycle-terms hint survive checkbox rebuilds (Task 3).
- **Create:** `tests/test_term_ay_scoping.py` — ordering + queryset-scoping + render tests (Tasks 1 & 2).

---

## Setup (once, before Task 1)

- [ ] **Branch off `main` in the submodule.**
  ```bash
  cd /repos/ewu/webapp/future_sections
  git checkout main && git pull
  git checkout -b feat/term-ay-scoping
  ```

---

## Task 1: Ask the AY selectors first; document the tie

**Files:**
- Modify: `future_sections/future_sections/settings/future_sections.py` (field declarations ≈lines 83–123)
- Test: `future_sections/future_sections/tests/test_term_ay_scoping.py` (create)

- [ ] **Step 1: Write the failing test**

Create `future_sections/future_sections/tests/test_term_ay_scoping.py`:

```python
from django.http import QueryDict
from django.test import TestCase, RequestFactory

from cis.models.term import AcademicYear, Term

from future_sections.future_sections.settings.future_sections import (
    future_sections as FSForm,
)


def _qdict(pairs):
    qd = QueryDict(mutable=True)
    for k, v in pairs:
        if isinstance(v, (list, tuple)):
            for vv in v:
                qd.appendlist(k, vv)
        else:
            qd[k] = v
    return qd


class TermFieldOrderTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/?report_id=1')

    def test_ay_selectors_precede_their_term_lists(self):
        keys = list(FSForm(self.request).fields.keys())
        self.assertLess(keys.index('academic_year'), keys.index('cycle_terms'))
        self.assertLess(
            keys.index('previous_academic_year'), keys.index('lookback_terms'))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_term_ay_scoping.TermFieldOrderTests -v 2`
Expected: FAIL — today `academic_year` is declared *after* `cycle_terms`, so `keys.index('academic_year') > keys.index('cycle_terms')` and `assertLess` fails.

- [ ] **Step 3: Reorder the field declarations and update help text**

In `future_sections/future_sections/settings/future_sections.py`, the four fields currently appear in this order: `cycle_terms`, `lookback_terms`, `academic_year`, `previous_academic_year` (followed by `term_mapping`). Replace that whole block so the two AY selectors come first and the term fields reference them. The exact replacement block (declaration order matters — it drives the on-screen layout):

```python
    academic_year = forms.ModelChoiceField(
        queryset=None,
        label="Requesting Information For",
        help_text='Select the academic year you are collecting section request information for',
        required=True
    )

    previous_academic_year = forms.ModelChoiceField(
        queryset=None,
        label="Previous Year Reference",
        help_text='Select a prior academic year to show what was previously offered at the high school',
        required=True
    )

    cycle_terms = forms.ModelMultipleChoiceField(
        queryset=Term.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label='Cycle Terms',
        help_text='Terms this cycle is collecting forecasts for. Scoped to the '
                  '"Requesting Information For" academic year selected above — only '
                  'that year\'s terms are shown. Schools that run once per AY pick '
                  'all terms in the AY; schools that run per semester pick one term '
                  'and re-open the cycle for the next.',
    )

    lookback_terms = forms.ModelMultipleChoiceField(
        queryset=Term.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Lookback Terms',
        help_text='Terms used to determine which teachers are expected to '
                  'respond (teachers who taught an Active ClassSection in any of '
                  'these terms). Scoped to the "Previous Year Reference" academic '
                  'year selected above — only that year\'s terms are shown.',
    )

    term_mapping = forms.CharField(
        max_length=2000,
        required=False,
        label="Term Mapping",
        widget=forms.HiddenInput(),
        initial='{}',
    )
```

> Note: the initial `queryset` on the two term fields changes from `Term.objects.none()`/all to `Term.objects.none()` here — that's only the class-level default; `__init__` (Task 2) sets the real queryset on every instantiation. Also note `term_mapping` stays immediately after `lookback_terms`, so the existing layout loop that injects the Term-Mapping UI before the `term_mapping` key (≈line 788) is unaffected.

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_term_ay_scoping.TermFieldOrderTests -v 2`
Expected: PASS (1 test).

- [ ] **Step 5: Run the existing cycle-terms tests to confirm no regression**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_cycle_terms_settings -v 2`
Expected: PASS (4 tests) — reordering declarations doesn't change validation, but `__init__` still sets the full queryset today, so these pass until Task 2 (where the bound-form path is explicitly preserved).

- [ ] **Step 6: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/settings/future_sections.py future_sections/tests/test_term_ay_scoping.py
git commit -m "feat(settings): ask AY selectors before cycle/lookback term lists"
```

---

## Task 2: Scope term querysets to the saved AYs on render (keep full queryset on POST)

**Files:**
- Modify: `future_sections/future_sections/settings/future_sections.py` (`__init__`, the term-queryset block ≈lines 604–609)
- Test: `future_sections/future_sections/tests/test_term_ay_scoping.py` (append a test class)

- [ ] **Step 1: Write the failing tests**

Append to `future_sections/future_sections/tests/test_term_ay_scoping.py`:

```python
class TermQuerysetScopingTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get('/?report_id=1')
        self.ay_req = AcademicYear.objects.create(name='2026-2027')
        self.ay_prev = AcademicYear.objects.create(name='2025-2026')
        self.req_fall = Term.objects.create(
            code='FA26', label='Fall 2026', academic_year=self.ay_req)
        self.req_spring = Term.objects.create(
            code='SP27', label='Spring 2027', academic_year=self.ay_req)
        self.prev_fall = Term.objects.create(
            code='FA25', label='Fall 2025', academic_year=self.ay_prev)

    def test_unbound_cycle_terms_scoped_to_requesting_ay(self):
        form = FSForm(self.request, initial={
            'academic_year': str(self.ay_req.id),
            'previous_academic_year': str(self.ay_prev.id),
        })
        cycle_ids = {str(t.id) for t in form.fields['cycle_terms'].queryset}
        self.assertEqual(
            cycle_ids, {str(self.req_fall.id), str(self.req_spring.id)})

    def test_unbound_lookback_terms_scoped_to_previous_ay(self):
        form = FSForm(self.request, initial={
            'academic_year': str(self.ay_req.id),
            'previous_academic_year': str(self.ay_prev.id),
        })
        lookback_ids = {str(t.id) for t in form.fields['lookback_terms'].queryset}
        self.assertEqual(lookback_ids, {str(self.prev_fall.id)})

    def test_unbound_without_initial_is_empty(self):
        form = FSForm(self.request)
        self.assertEqual(form.fields['cycle_terms'].queryset.count(), 0)
        self.assertEqual(form.fields['lookback_terms'].queryset.count(), 0)

    def test_render_shows_only_requesting_ay_terms(self):
        form = FSForm(self.request, initial={
            'academic_year': str(self.ay_req.id),
            'previous_academic_year': str(self.ay_prev.id),
        })
        html = str(form['cycle_terms'])
        self.assertIn('Fall 2026', html)
        self.assertIn('Spring 2027', html)
        self.assertNotIn('Fall 2025', html)

    def test_bound_form_keeps_full_queryset_for_validation(self):
        # On POST self.initial is empty; the queryset must stay full so
        # field.clean() accepts any valid term id (clean_* do the real work).
        data = _qdict([('cycle_terms', [str(self.req_fall.id)])])
        form = FSForm(self.request, data=data)
        self.assertEqual(
            form.fields['cycle_terms'].queryset.count(), Term.objects.count())
        self.assertEqual(
            form.fields['lookback_terms'].queryset.count(), Term.objects.count())

    def test_bound_valid_cycle_terms_not_rejected(self):
        data = _qdict([
            ('cycle_terms', [str(self.req_fall.id), str(self.req_spring.id)]),
        ])
        form = FSForm(self.request, data=data)
        form.is_valid()
        self.assertNotIn('cycle_terms', form.errors)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_term_ay_scoping.TermQuerysetScopingTests -v 2`
Expected: FAIL — today `__init__` sets both term querysets to `Term.objects.all()` unconditionally, so `test_unbound_*_scoped_*`, `test_unbound_without_initial_is_empty`, and `test_render_shows_only_requesting_ay_terms` all fail (they see every term). (`test_bound_*` already pass under the current all-terms behavior.)

- [ ] **Step 3: Implement the bound/unbound queryset split**

In `future_sections/future_sections/settings/future_sections.py`, inside `__init__`, replace the current block:

```python
        # Newest academic year first, then by code ascending within each AY so
        # terms appear roughly chronological under their year header.
        _term_order = Term.objects.all().order_by('-academic_year__name', 'code')
        self.fields['cycle_terms'].queryset = _term_order
        self.fields['lookback_terms'].queryset = _term_order
```

with:

```python
        # Cycle Terms are scoped to the "Requesting Information For" AY and
        # Lookback Terms to the "Previous Year Reference" AY.
        #
        # On a BOUND form (POST/save) keep the full term queryset: Django's
        # ModelMultipleChoiceField.clean() rejects any submitted id not in the
        # queryset *before* clean_cycle_terms/clean_lookback_terms run, and those
        # custom cleaners + clean() are what actually enforce the rules. Narrowing
        # the queryset here would make every save fail with "not a valid choice".
        #
        # On an UNBOUND form (initial render) scope each list to its saved AY so
        # the checkbox lists stay short; the JS in settings.js re-fetches and
        # rebuilds a list whenever its AY dropdown changes.
        if self.is_bound:
            full_terms = Term.objects.all().order_by('-academic_year__name', 'code')
            self.fields['cycle_terms'].queryset = full_terms
            self.fields['lookback_terms'].queryset = full_terms
        else:
            saved = self.initial or {}
            req_ay = saved.get('academic_year')
            prev_ay = saved.get('previous_academic_year')
            self.fields['cycle_terms'].queryset = (
                Term.objects.filter(academic_year__id=req_ay).order_by('code')
                if req_ay else Term.objects.none()
            )
            self.fields['lookback_terms'].queryset = (
                Term.objects.filter(academic_year__id=prev_ay).order_by('code')
                if prev_ay else Term.objects.none()
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_term_ay_scoping -v 2`
Expected: PASS (1 ordering test + 6 scoping tests = 7).

- [ ] **Step 5: Re-run the existing cycle-terms tests (regression)**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests.test_cycle_terms_settings -v 2`
Expected: PASS (4 tests) — they are bound forms, so they hit the full-queryset branch.

- [ ] **Step 6: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/settings/future_sections.py future_sections/tests/test_term_ay_scoping.py
git commit -m "feat(settings): scope cycle/lookback term lists to their academic year on render"
```

---

## Task 3: Rebuild a term list in the browser when its AY dropdown changes

**Files:**
- Modify: `future_sections/future_sections/staticfiles/future_sections/js/settings.js`

> **No JS unit-test harness exists in this repo** (the test suite is Django/unittest only). Task 2's render test already locks the server-side contract (initial list = saved AY's terms). This task wires the live re-filtering and is verified manually in Step 4 and in Task 4's integration check. Do not invent a JS test runner.

- [ ] **Step 1: Add the AY-scoped term rebuild functions**

In `future_sections/future_sections/staticfiles/future_sections/js/settings.js`, add these two functions immediately **after** `initTermFieldScrollContainer` (≈line 486, before `initCycleTermsHint`):

```javascript
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
```

- [ ] **Step 2: Make the cycle-terms hint survive checkbox rebuilds**

Still in `settings.js`, replace the entire existing `initCycleTermsHint` function (≈lines 488–520) with this version (uses a delegated `change` handler and locates the field group by id, so it keeps working after a rebuild replaces the checkboxes):

```javascript
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
```

- [ ] **Step 3: Register `initAyScopedTerms` in `initAll`**

Still in `settings.js`, in the `inits` array inside `initAll()` (≈lines 522–533), add `initAyScopedTerms` (place it right after `initCycleTermsHint`):

```javascript
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
```

- [ ] **Step 4: Collect static and manually verify in the browser**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py collectstatic --noinput`

Then in the CE portal open **Settings → Classes → Section Requests** and confirm:
1. **Order:** "Requesting Information For" and "Previous Year Reference" dropdowns appear **above** the Cycle Terms and Lookback Terms checkbox lists.
2. **Initial scope:** With a saved config, Cycle Terms lists only the requesting year's terms (saved ones checked); Lookback Terms lists only the previous year's terms.
3. **Live re-filter:** Change "Requesting Information For" to a different AY → the Cycle Terms list rebuilds to that year's terms. Change "Previous Year Reference" → the Lookback Terms list rebuilds. (Open DevTools Network tab: each change fires `GET /ce/api/term/?academic_year=…`.)
4. **Save round-trip:** Pick an AY, check one or more terms, Save. Reopen the setting and confirm the AY + checked terms persisted, and the lists are still scoped. (Browser cache can serve a stale `settings.js`; hard-refresh if behavior looks off.)

- [ ] **Step 5: Commit**

```bash
cd /repos/ewu/webapp/future_sections
git add future_sections/staticfiles/future_sections/js/settings.js
git commit -m "feat(settings): rebuild cycle/lookback term lists when their AY dropdown changes"
```

---

## Task 4: Full regression + no-migration / no-packaging verification

**Files:** none (verification only)

- [ ] **Step 1: Confirm no model migration is produced**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py makemigrations future_sections`
Expected: `No changes detected in app 'future_sections'`.
(If a migration is generated, STOP — nothing in this plan adds a model field.)

- [ ] **Step 2: Run the full future_sections test suite (no regressions)**

Run: `docker exec -w /app/webapp django_web_ewu python manage.py test future_sections.future_sections.tests -v 1`
Expected: all existing tests + the new `test_term_ay_scoping` tests pass.

- [ ] **Step 3: Confirm packaging is untouched**

Run:
```bash
cd /repos/ewu/webapp/future_sections
git status --short
```
Expected: only `settings/future_sections.py`, `staticfiles/future_sections/js/settings.js`, the new `tests/test_term_ay_scoping.py`, and this plan doc changed/added. No edits to `MANIFEST.in`, `setup.cfg`, or `setup.py`. The `submod-package-manifest` skill does not apply.

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch. The submodule's default branch is `main`; per repo flow open a PR from `feat/term-ay-scoping` (do not push/merge without confirmation). After the submodule change is released/tagged, the host tenant repos pick it up via their pinned `git+https://…@<tag>` requirement.

---

## Self-Review

**Spec coverage:**
- "cycle terms and lookback terms are getting long" → Task 2 scopes each rendered list to a single AY (a handful of terms) instead of all terms across all years. ✓
- "tie those terms to requesting information for and previous year reference" → cycle_terms ↔ `academic_year` ("Requesting Information For"), lookback_terms ↔ `previous_academic_year` ("Previous Year Reference"), enforced in `__init__` (server) + `AY_TERM_PAIRS` (JS), and documented in each field's help text (Task 1). ✓
- "those 2 should be asked first" → Task 1 reorders declarations so both AY selectors precede both term lists; the crispy layout follows declaration order. Verified by `test_ay_selectors_precede_their_term_lists`. ✓
- "based on what academic year is selected only show the terms for those" → server pre-filters on render (Task 2) + JS rebuilds on AY change from `/ce/api/term/` (Task 3). ✓

**Placeholder scan:** Every code step shows the exact code; every run step shows the exact container command and expected output. The one place without an automated test (JS) is explicitly called out with a manual verification procedure, because no JS test harness exists.

**Type/name consistency:** Field names `academic_year`, `previous_academic_year`, `cycle_terms`, `lookback_terms` are used identically in the form, the queryset split, the tests, and the JS `AY_TERM_PAIRS` (`#id_<field>` selectors + checkbox `name="<field>"`). The endpoint `/ce/api/term/` and its `{id, label}` response shape match `TermViewSet`/`TermSerializer` and the existing `initTermMapping` usage. The bound/unbound branch keys (`self.is_bound`, `self.initial`) match Django's form API and the `setting` app's `report_class(request, initial=…)` vs `report_class(request, request.POST)` call sites.

**Critical correctness note carried into the plan:** the bound-form path **must** keep the full term queryset (Task 2, Step 3) — narrowing it would break every save because `ModelMultipleChoiceField.clean()` validates submitted ids against the queryset before the custom `clean_*` methods run. This is why Task 2 splits on `self.is_bound` rather than always scoping.
