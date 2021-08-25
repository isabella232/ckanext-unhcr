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
