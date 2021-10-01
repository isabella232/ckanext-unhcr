$( document ).ready(function() {

  /*
  Toggle status badges
  */
  $(document).on("click", ".kobo-resource-status", function(){
    $this = $(this);
    if ($this.data('status') != 'complete' && ! $this.data('block-toggle')) {
      let resource_id = $this.data("resource-id");
      $("#kobo-item-info-" + resource_id).toggle();
    }
  });

  mark_all_pending = function() {
    // Mark all KoBo resources as pending
    as_pending = 'sync pending <img src="/base/images/loading.gif" style="height:auto; width: 15px; margin:5px;"/>';
    $(".kobo-resource-status").html(as_pending);
    $(".kobo-resource-status").removeClass('kobo-resource-complete kobo-resource-stalled kobo-resource-error');
    $(".kobo-resource-status").addClass('kobo-resource-pending');
    $(".kobo-resource-status").data('block-toggle', true)
    $(".kobo-item-info").hide();
  }

  $(".flash-messages").after(' \
      <div class="dynamic-flash-messages"> \
      <img id="loading" src="/base/images/loading.gif" \
      style="height:auto; width: 30px; margin-right:20px; display: none;"/> \
      <span id="real-flash-msg"></span> \
      </div>'
  );
  /* 
  Check if there are new submissions
  */

  $(document).on("click", ".kobo-pkg-update-resources", function(){
      $(".dynamic-flash-messages").addClass('alert alert-success')
      $("#loading").show();
      $("#real-flash-msg").html('Checking for updates');
      
      $this = $(this);
      $this.attr("disabled", true);
      let kobo_asset_id = $this.data('kobo-asset-id');
      let url = $this.data('kobo-update-endpoint');
      let force = $this.data('force');

      $.ajax(
          {
            url: url,
            type: 'POST',
            data: {"kobo_asset_id": kobo_asset_id, "force": force},
            success: function (data) {
              $this.removeAttr("disabled");
              if (! data.forced) {
                if (data.new_submissions == 0) {
                  msg = 'There are no new submissions. You can still <b>force</b> the update to get the latest changes in the submissions';
                  $this.find('.update-kobo-button-text').html('Force update KoBoToolbox data');
                  $this.data('force', "true");
                  $this.css('background-color', '#d85a5a');
                  $this.css('color', 'white');
                } else {
                  msg = 'There are ' + data.new_submissions + ' new submissions.';
                  msg += '<br/>Update survey job started successfully. The resources will be updated in a few minutes.';
                  $this.hide();
                  mark_all_pending();
                }
              } else {
                msg = 'Forced update survey job started successfully. The resources will be updated in a few minutes.';
                $this.hide();
                mark_all_pending();
              }
              $("#loading").hide();
              $("#real-flash-msg").html(msg);
            },
            error: function (xhr) {
              $(".dynamic-flash-messages").addClass('alert-danger');
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
