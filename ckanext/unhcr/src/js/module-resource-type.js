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
      this.new_kobo_dataset = $('.kobo-resources-publish').length > 0;
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
        // also show the release button for KoBo if exists
        if (this.new_kobo_dataset) {
          $('.form-actions').css('display', 'inline');
          $('.kobo-resources-publish').nextAll().hide();
        }
      }
    },

    _onDataButtonClick: function (ev) {
      if (ev) ev.preventDefault()
      this.field.hide()
      // for new KoBo datasets, hide "release" and show "finish"
      if (this.new_kobo_dataset) {
        $('.kobo-resources-publish').hide();
        $('.kobo-resources-publish').nextAll().show();
      }
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
      // for new KoBo datasets, hide "release" and show "finish"
      if (this.new_kobo_dataset) {
        $('.kobo-resources-publish').hide();
        $('.kobo-resources-publish').nextAll().show();
      }
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
