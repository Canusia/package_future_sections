function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
          const cookie = cookies[i].trim();
          if (cookie.substring(0, name.length + 1) === (name + '=')) {
              cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
              break;
          }
      }
  }
  return cookieValue;
}

(function($) {
    'use strict';

    var config = $('#future-sections-config');
    var markTeachingUrl = config.data('mark-teaching-url');
    var markNotTeachingUrl = config.data('mark-not-teaching-url');
    var removeTeachingStatusUrl = config.data('remove-teaching-status-url');
    var addTeacherUrl = config.data('add-teacher-url');
    var adminAssignUrl = config.data('admin-assign-url');
    var adminPositionsUrl = config.data('admin-positions-url');
    var courseRequestsUrl = config.data('course-requests-url');
    var confirmSectionsUrl = config.data('confirm-sections-url');
    var confirmAdministratorsUrl = config.data('confirm-administrators-url');
    var highschoolIds = config.data('highschool-ids') ? String(config.data('highschool-ids')).split(',') : [];
    var roleIds = config.data('role-ids') ? String(config.data('role-ids')).split(',') : [];
    var windowIsOpen = config.data('window-is-open') === true || config.data('window-is-open') === 'true';

    // Map action names to their API endpoints
    function getActionUrl(action) {
        switch (action) {
            case 'teaching-section':
                return markTeachingUrl;
            case 'not-teaching-section':
                return markNotTeachingUrl;
            case 'remove-not-teaching-section':
                return removeTeachingStatusUrl;
            case 'add_new_teacher':
            case 'add_new_teacher_choice':
            case 'add_new_teacher_facilitator':
                return addTeacherUrl;
            case 'edit_highschool_admin_role':
                return adminAssignUrl;
            default:
                return null;
        }
    }

    // DataTable instance for course requests
    var coursesTable = null;

    function renderOfferingStatus(data, type, row) {
        var offeringStatus = row.offering_status;
        var sections = row.sections || [];
        var certId = row.certificate_id;
        var academicYearId = row.academic_year_id;

        // No offering status set yet - show action buttons
        if (!offeringStatus) {
            if (!windowIsOpen) {
                return '---';
            }
            return '<button type="button" class="btn btn-sm btn-primary course-action" ' +
                'data-academic_year="' + academicYearId + '" ' +
                'data-toggle="modal" ' +
                'data-course-certificate="' + certId + '" ' +
                'data-id="-1" ' +
                'data-action="teaching-section" ' +
                'data-target="#teachingModal">' +
                'Enter Course Details</button> ' +
                '<button type="button" class="btn btn-sm btn-secondary mt-xs-1 course-action" ' +
                'data-course-certificate="' + certId + '" ' +
                'data-academic_year="' + academicYearId + '" ' +
                'data-action="not-teaching-section" ' +
                'data-id="-1">' +
                'We are not teaching this course</button>';
        }

        // Marked as not teaching
        if (offeringStatus === 'no') {
            var html = 'Marked as not offering';
            if (windowIsOpen) {
                html += ' <a title="Delete not offering info" class="float-right course-action" ' +
                    'data-confirm="1" data-course-certificate="' + certId + '" ' +
                    'data-academic_year="' + academicYearId + '" ' +
                    'data-action="remove-not-teaching-section" href="#">' +
                    '<i class="fas fa fa-trash"></i></a>';
            }
            return html;
        }

        // Marked as teaching
        var html = 'Marked as Offering';
        if (windowIsOpen) {
            html += '<a title="Delete offering info" class="float-right course-action" ' +
                'data-confirm="1" data-course-certificate="' + certId + '" ' +
                'data-academic_year="' + academicYearId + '" ' +
                'data-action="remove-not-teaching-section" href="#">' +
                '<i class="fas fa fa-trash"></i></a>';
            html += '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<a title="Edit Info" class="float-right course-action" ' +
                'data-toggle="modal" data-target="#teachingModal" ' +
                'data-course-certificate="' + certId + '" ' +
                'data-academic_year="' + academicYearId + '" ' +
                'data-action="teaching-section" href="#">' +
                '<i class="fas fa fa-edit"></i>&nbsp;Edit&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</a>&nbsp;';
        }

        // Show section details using pre-formatted display from settings
        var sectionDisplay = row.section_display || [];
        $.each(sectionDisplay, function(k, displayText) {
            if (displayText) {
                html += '<br>' + displayText;
            }
        });

        return html;
    }

    function initCoursesDataTable() {
        var $table = $('#tbl_course_requests');
        if (!courseRequestsUrl || $table.length === 0) {
            return;
        }

        coursesTable = $table.DataTable({
            language: {
                'emptyTable': 'No course requests found.'
            },
            ajax: courseRequestsUrl + '?format=datatables',
            columns: [
                {
                    data: 'course_title',
                    render: function(data, type, row) {
                        return data || '---';
                    }
                },
                {
                    data: 'teacher_name',
                    render: function(data, type, row) {
                        return data || '---';
                    }
                },
                {
                    data: 'status',
                    render: function(data, type, row) {
                        return data || '---';
                    }
                },
                {
                    data: 'highschool_name',
                    render: function(data, type, row) {
                        return data || '---';
                    }
                },
                {
                    data: null,
                    orderable: false,
                    render: renderOfferingStatus
                }
            ]
        });
    }

    function reloadCoursesTable() {
        if (coursesTable) {
            coursesTable.ajax.reload(null, false);
        }
    }

    // DataTable instance for school personnel
    var personnelTable = null;

    function buildAdminPositionsUrl() {
        // Build query string with arrays
        var params = ['format=datatables'];
        highschoolIds.forEach(function(id) {
            if (id) params.push('highschool_ids=' + encodeURIComponent(id));
        });
        roleIds.forEach(function(id) {
            if (id) params.push('role_ids=' + encodeURIComponent(id));
        });
        return adminPositionsUrl + '?' + params.join('&');
    }

    function initPersonnelDataTable() {
        // Skip if no roles configured or table doesn't exist
        var $table = $('#tbl_school_personnel_list');

        var windowIsOpen = $table.data('window-is-open') === true || $table.data('window-is-open') === 'true';

        personnelTable = $table.DataTable({
            language: {
                'emptyTable': 'No personnel records found.'
            },
            ajax: buildAdminPositionsUrl(),
            columns: [
                {
                    data: 'highschool_name',
                    render: function(data, type, row) {
                        return data || '---';
                    }
                },
                {
                    data: 'position_name',
                    render: function(data, type, row) {
                        return data || '---';
                    }
                },
                {
                    data: 'admin_name',
                    render: function(data, type, row) {
                        if (data) {
                            return data + '<br>' + (row.admin_email || '');
                        }
                        return '---';
                    }
                },
                {
                    data: null,
                    orderable: false,
                    searchable: false,
                    render: function(data, type, row) {
                        if (!windowIsOpen) {
                            return '';
                        }
                        return '<a title="Edit role" class="btn btn-sm btn-primary course-action" ' +
                            'data-role="' + row.position_id + '" ' +
                            'data-highschool="' + row.highschool_id + '" ' +
                            'data-target="#teachingModal" ' +
                            'data-action="edit_highschool_admin_role" ' +
                            'href="#">' +
                            '<i class="fas fa-pencil"></i>&nbsp;Edit</a>';
                    }
                }
            ]
        });
    }

    function reloadPersonnelTable() {
        if (personnelTable) {
            personnelTable.ajax.reload(null, false);
        }
    }

    $(document).ready(function() {
        initCoursesDataTable();
        initPersonnelDataTable();

        // Ajax form submit handler
        $(document).on('submit', 'form.frm_ajax', function(event) {
            var blocked_element = $(this).parent();
            $(blocked_element).block();
            event.preventDefault();

            var form = $(this);

            // Clear previous validation errors
            if ($('input, select, textarea').hasClass('is-invalid')) {
                $('input, select, textarea').removeClass('is-invalid');
            }

            if ($('input, select, textarea').next('p').length) {
                $('input, select, textarea').nextAll('p').empty();
            }

            var action = $(form).attr('action');
            var first_element = '';

            // Use FormData to handle file uploads
            var formData = new FormData(form[0]);

            $.post({
                url: action,
                type: 'POST',
                data: formData,
                processData: false,
                contentType: false,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                },
                error: function(xhr, status, error) {
                    var errors = $.parseJSON(xhr.responseJSON.errors);

                    var span = document.createElement('span');
                    span.innerHTML = '';

                    for (var name in errors) {
                        for (var i in errors[name]) {
                            var $input = $("[name='" + name + "']");
                            $input.addClass('is-invalid');
                            $input.after("<p class='invalid-feedback'><strong class=''>" + errors[name][i].message + "</strong></p>");
                        }

                        if (name == '__all__') {
                            span.innerHTML += '<br><br>' + errors[name][0].message;
                        }

                        if (first_element == '') {
                            $input.focus();
                        } else {
                            first_element = '-';
                        }
                    }

                    swal({
                        title: xhr.responseJSON.message,
                        content: span,
                        icon: 'warning'
                    });

                    $(blocked_element).unblock();
                },
                success: function(response) {
                    swal({
                        icon: 'success',
                        title: 'Success',
                        text: response.message,
                        type: response.status
                    }).then(function(value) {
                        window.closeTeachingModal();
                        reloadCoursesTable();
                        reloadPersonnelTable();
                    });
                    $(blocked_element).unblock();
                }
            });
            return false;
        });

        // Course action click handler
        $(document).on('click', '.course-action', function() {
            var action = $(this).attr('data-action');
            var modal = $(this).attr('data-target');

            // Build request data with new parameter names
            var data = {
                'course_certificate_id': $(this).attr('data-course-certificate'),
                'academic_year_id': $(this).attr('data-academic_year'),
                'role_id': $(this).attr('data-role'),
                'highschool_id': $(this).attr('data-highschool')
            };

            // Handle course_type for add_new_teacher variants
            if (action === 'add_new_teacher_choice') {
                data['course_type'] = 'cccl';
            } else if (action === 'add_new_teacher_facilitator') {
                data['course_type'] = 'facilitator';
            } else if (action === 'add_new_teacher') {
                data['course_type'] = 'pathways';
            }

            var actionUrl = getActionUrl(action);
            if (!actionUrl) {
                console.error('Unknown action: ' + action);
                return;
            }

            if ($(this).attr('data-confirm') == '1') {
                if (!confirm('Are you sure you want to do this? This action cannot be undone')) {
                    return;
                }
            }

            $.blockUI();
            $.ajax({
                type: 'GET',
                url: actionUrl,
                data: data,
                success: function(response) {
                    $.unblockUI();
                    if (response.display == 'swal') {
                        swal('Success', response.message, 'success').then(function() {
                            reloadCoursesTable();
                            reloadPersonnelTable();
                        });
                    } else {
                        $(modal + ' .modal-content > .modal-body').html(response);
                        $(modal).modal('show');
                    }
                },
                error: function(response) {
                    $.unblockUI();
                    alert('Failed request');
                }
            });
        });
    });

    // Global function to close modal (called from iframe)
    window.closeTeachingModal = function() {
        $('#teachingModal').modal('hide');
    };

})(jQuery);
