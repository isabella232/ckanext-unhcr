$( document ).ready(function() {

  // Activate select2 widget
  if ($('#field-linked-datasets').length > 0) {
    $('#field-linked-datasets').select2({
      placeholder: 'Click to get a drop-down list or start typing a dataset title'
    });
  }

});
