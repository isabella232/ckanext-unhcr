$( document ).ready(function() {

  // toggle account menu
  $( ".account-masthead .account" ).click(function() {
    $( this ).toggleClass( "active" );
  });

  // toggle login information
  $( ".login-splash .toggle a" ).click(function() {
    $( this ).parents(".info").toggleClass( "active" );
  });

});

// Validation
$(document).ready(function() {

  // Get fields
  var fields = $('.curation-validation ul[data-fields]').data('fields') || [];

  // Stop if no fields
  if (!fields.length) {
    return
  }

  // Highlight in form
  for (var field of fields) {
    var group = $(`[name="${field}"]`).closest('.control-group');
    group.addClass('curation-invalid');
    group.find('.controls').append(
      `<div class="info-block curation-info-block">
        <i class="fa fa-times"></i>
        This field need to be updated before the dataset can be published
      </div>`
    );
  }

});

// Header
$(document).ready(function() {
  var sidebar = $('.curation-data-deposit');
  if (sidebar.length) {
    var predicat = function() {return $(this).text() === "Data Deposit";}
    $('.navigation a').filter(predicat).parent().addClass('active');
  }
});

$( document ).ready(function() {

  // set default state
  //$(".hierarchy-tree").parent("li").addClass( "open" ); // open
  $(".hierarchy-tree").addClass('collapse').parent("li").addClass( "closed" ); // closed

  // add toggle button
  $( ".hierarchy-tree" ).prev().before(
    '<button class="hierarchy-toggle"><span>Expand / collapse<span></button>'
  );

  // let CSS know that this has happened
  $(".hierarchy-tree-top").addClass('has-toggle');

  // toggle on click
  $( ".hierarchy-toggle" ).click(function() {
    $( this ).siblings(".hierarchy-tree").collapse('toggle');
    $( this ).parent("li").toggleClass( "open closed" )
  });

  // auto expand parents of highlighted
  $(".hierarchy-tree-top .highlighted").parents(".closed").removeClass("closed").addClass("open").children(".hierarchy-tree").removeClass("collapse");
});

$( document ).ready(function() {

  // Activate select2 widget
  // We can't use programmatically generated
  // select html field because it requires select2@4.0
  $('#field-data_collector').select2({
    placeholder: 'Click to get a drop-down list or start typing a data collector title',
    width: '100%',
    multiple: true,
    tokenSeparators: [','],
    tags: [
      "United Nations High Commissioner for Refugees",
      "Action contre la faim",
      "Impact - REACH",
      "Agency for Technical Cooperation and Development",
      "CARE International",
      "Caritas",
      "Danish Refugee Council",
      "INTERSOS",
      "International Organization for Migration",
      "Mercy Corps",
      "Norwegian Refugee Council ",
      "Save the Children International",
      "MapAction",
      "CartONG",
      "iMMAP",
      "Office of the High Commissioner for Human Rights",
      "Food and Agriculture Organization",
      "United Nations Assistance Mission for Iraq",
      "United Nations Development Programme",
      "United Nations Educational, Scientific and Cultural Organization",
      "Union Nationale des Femmes de Djibouti",
      "United Nations Populations Fund",
      "UN-HABITAT",
      "United Nations Humanitarian Air Service",
      "United Nations Children's Fund",
      "United Nations Industrial Development Organization",
      "UNITAR/UNOSAT",
      "United Nations Mine Action Coordination Centre",
      "United Nations Mission in Liberia",
      "United Nations Mission in South Sudan",
      "United Nations Office for the Coordination of Humanitarian Affairs",
      "United Nations Office for Project Services",
      "UN Office for West Africa and the Sahel",
      "United Nations Relief and Works Agency ",
      "UN Security Council",
      "UNV",
      "UN Women",
      "World food Programme - Programme Alimentaire Mondial",
      "World Health Organization",
      "World Bank",
    ]
  });

});

$( document ).ready(function() {

  // Activate select2 widget
  $('#field-linked-datasets').select2({
    placeholder: 'Click to get a drop-down list or start typing a dataset title'
  });

});

$( document ).ready(function() {

  // Activate select2 widget
  $('#membership-username')
    .on('change', function(ev) {
      $(ev.target.form).submit();
    })
    .select2({
      placeholder: 'Click or start typing a user name',
    });

  // Activate select2 widget
  $('#membership-contnames')
    .on('change', function(ev) {
      toggleAddMembershipButton();
    })
    .select2({
      placeholder: 'Click or start typing a container name',
    });

  // Activate select2 widget
  $('#membership-role')
    .on('change', function(ev) {
      toggleAddMembershipButton();
    })
    .select2({
      placeholder: 'Click or start typing a role name',
    });

  function toggleAddMembershipButton() {
    if ($('#membership-contnames').val() && $('#membership-role').val()) {
      $('#membership-button').attr('disabled', false)
    } else {
      $('#membership-button').attr('disabled', true)
    }
  }

});

this.ckan.module('resource-type', function ($) {
  return {

    // Public

    options: {
      value: null,
    },

    initialize: function () {

      // Get main elements
      this.field = $('#field-resource-type')
      this.input = $('input', this.field)

      // Add event listeners
      $('button.btn-data', this.field).click(this._onDataButtonClick.bind(this))
      $('button.btn-attachment', this.field).click(this._onAttachmentButtonClick.bind(this))
      $('button:contains("Previous")').click(this._onPreviousButtonClick.bind(this))

      // Emit initialized
      this._onIntialized()

    },

    // Private

    _onIntialized: function () {
      if (this.options.value === 'data') {
        this._onDataButtonClick()
      } else if (this.options.value === 'attachment') {
        this._onAttachmentButtonClick()
      } else {
        this.field.nextAll().hide()
        this.field.show()
      }
    },

    _onDataButtonClick: function (ev) {
      if (ev) ev.preventDefault()
      this.field.hide()
      this.field.nextAll().show()
      // We allow to select only the "Microdata" option
      $('#field-file_type option').each(function () {
        if ($(this).val() !== 'microdata') {
          $(this).remove();
        }
      })
      this.input.val('data')
      this._fixUploadButton()
      this._hideLinkButton()
      this._appendUploadSizeInfoBlock()
    },

    _onAttachmentButtonClick: function (ev) {
      if (ev) ev.preventDefault()
      this.field.hide()
      this.field.nextAll().show()
      // We hide all the fields below "File Type"
      $('#field-file_type').parents('.form-group').nextAll('.form-group').hide()
      // We allow to select only NOT the "Microdata" option
      $('#field-file_type option').each(function () {
        if ($(this).val() === 'microdata') {
          $(this).remove();
        }
      })
      this.input.val('attachment')
      this._fixUploadButton()
      this._appendUploadSizeInfoBlock()
    },

    _onPreviousButtonClick: function (ev) {
      if (ev) ev.preventDefault()
      this._onIntialized()
    },

    _fixUploadButton: function () {
      // https://github.com/ckan/ckan/blob/master/ckan/public/base/javascript/modules/image-upload.js#L88
      // Ckan just uses an input field behind a button to mimic uploading after a click
      // Our resources setup breakes the width calcucations so we fix it here
      var input = $('#field-image-upload')
      input.css('width', input.next().outerWidth()).css('cursor', 'pointer')
    },

    _hideLinkButton: function() {
      $('.dataset-resource-form div.image-upload a:last-child').hide()
    },

    _appendUploadSizeInfoBlock: function() {
      $("#upload-size-info-block").insertAfter(
        $("#field-image-upload").siblings(":last")
      ).show()
    }

  };
});

$( document ).ready(function() {

  /* 
  Update file resources from KoBo is not allowed since their files are always directly imported from KoBo
  */
  let kobo_type = $('#kobo_type_field').val();
  if (kobo_type !== undefined && kobo_type != "") {
    // TODO: link to where you can re-import them
    msg = "You can change the resource metadata but the actual data files are imported from Kobo.";
    old_url = $('#field-image-url').val();
    preserve_url = "<input type='hidden' name='url' value='" + old_url + "'>";
    $('.image-upload').html('<div class="alert alert-warning">' + msg + '</div> ' + preserve_url);
  }

});

$( document ).ready(function() {

  /*
  kobo-pkg-update-resources button starts a job to update all resources
  with new submissions
  */
  $('.kobo-pkg-update-resources').click(
    function(evt) {
      $this = $(this);
      let kobo_asset_id = $this.data('kobo-asset-id');
      let url = $this.data('kobo-update-endpoint');
      $.ajax(
        {
          url: url,
          type: 'POST',
          data: {"kobo_asset_id": kobo_asset_id},
          success: function (data) {
            $("#update-kobo-resources-container-" + kobo_asset_id).html('Data import job started. Resources will be updated in a few minutes.');
            $("#update-kobo-resources-container-" + kobo_asset_id).addClass('alert alert-success running-kobo-update');
					},
					error: function (xhr) {
						alert('Failed to start a job to update this survey ' + xhr.responseJSON.error)
					}
        }
      );

    }
  )


});

$( document ).ready(function() {

  /* 
  Check if there are new submissions
  */
  base_html = '<img id="loading" src="/base/images/loading.gif" \
               style="height:auto; width: 30px; margin-right:20px; \
               display: none;"/> \
               <span id="real-flash-msg"></span>';
  $(".flash-messages").html(base_html);
  
  $('#kobo-pkg-update-resources').click(
    function(evt) {
      $("#loading").show();
      $(".flash-messages").addClass('alert alert-success');
      $("#real-flash-msg").html('Checking for updates');
      
      $this = $(this);
      $this.attr("disabled", true);
      let kobo_asset_id = $this.data('kobo-asset-id');
      let url = $this.data('kobo-update-endpoint');
      $.ajax(
          {
            url: url,
            type: 'POST',
            data: {"kobo_asset_id": kobo_asset_id},
            success: function (data) {
              if (data.new_submissions == 0) {
                $("#loading").hide();
                $("#real-flash-msg").html('There are no new submissions');
                $this.removeAttr("disabled");
              } else {
                msg = 'There are ' + data.new_submissions + ' new submissions.'
                msg += '<br/>Update survey job started successfully. The resources will be updated in a few minutes.'
                $("#loading").hide();
                $("#real-flash-msg").html(msg);
                
              }
            },
            error: function (xhr) {
              $(".flash-messages").addClass('alert-danger');
              $("#loading").hide();
              if (xhr.responseJSON) {
                $("#real-flash-msg").html('Failed to check updates for this survey. ' + xhr.responseJSON.error);
              } else {
                $("#real-flash-msg").html('Failed to check updates for this survey. Status ' + xhr.status);
              }
            }
          }
        );
      }
  );
  
  
});
