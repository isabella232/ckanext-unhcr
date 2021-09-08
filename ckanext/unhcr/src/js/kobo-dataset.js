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
