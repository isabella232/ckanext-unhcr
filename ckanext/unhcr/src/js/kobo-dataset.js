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

  mark_resource_pending = function(resource_status_elem, item_info_elem) {
    // Mark a single KoBo resources as pending
    as_pending = 'sync pending <img src="/base/images/loading.gif" style="height:auto; width: 15px; margin:5px;"/>';
    resource_status_elem.html(as_pending);
    resource_status_elem.removeClass('kobo-resource-complete kobo-resource-stalled kobo-resource-error');
    resource_status_elem.addClass('kobo-resource-pending');
    resource_status_elem.data('block-toggle', true)
    item_info_elem.hide();
  }

  $(".flash-messages").after(' \
      <div class="dynamic-flash-messages"> \
      <img id="loading" src="/base/images/loading.gif" \
      style="height:auto; width: 30px; margin-right:20px; display: none;"/> \
      <span id="real-flash-msg"></span> \
      </div>'
  );

  /* 
  Update all kobo resources
  */

  $(document).on("click", ".kobo-pkg-update-resources", function(){
      $(".dynamic-flash-messages").addClass('alert alert-success')
      $("#loading").show();
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
              $this.removeAttr("disabled");
              msg = 'Update survey job started successfully. The resources will be updated in a few minutes.';
              $this.hide();
              mark_all_pending();
              
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
  
    /* 
  Update a single kobo resource
  */

  $(document).on("click", ".kobo-update-resource", function(){
    $(".dynamic-flash-messages").addClass('alert alert-success')
    $("#loading").show();
    $("#real-flash-msg").html('Checking for resource update');
    
    $this = $(this);
    $this.attr("disabled", true);
    let kobo_resource_id = $this.data('kobo-resource-id');
    let url = $this.data('kobo-update-endpoint');
    
    $.ajax(
        {
          url: url,
          type: 'POST',
          data: {"kobo_resource_id": kobo_resource_id},
          success: function (data) {
            $this.removeAttr("disabled");
            msg = 'Update survey job started successfully. This resource will be updated in a few minutes.';
            $this.hide();
            //define which element to mark as "in progress"
            $resource_status = $("#kobo-resource-status-" + kobo_resource_id)
            $item_info = $("#kobo-item-info-" + kobo_resource_id)
            mark_resource_pending($resource_status, $item_info);
            
            $("#loading").hide();
            $("#real-flash-msg").html(msg);
          },
          error: function (xhr) {
            $(".dynamic-flash-messages").addClass('alert-danger');
            $("#loading").hide();
            if (xhr.responseJSON) {
              $("#real-flash-msg").html('Failed to check updates for this resource. ' + xhr.responseJSON.error);
            } else {
              $("#real-flash-msg").html('Failed to check updates for this resource. Status ' + xhr.status);
            }
          }
        }
      );
    }
);

  $(document).on("click", "#kobo-import-settings-title", function(){
    $this = $(this);
    $("#kobo-import-settings").toggle();
  });

  // hide all toggables
  let $togglables = $(".togglable");
  $togglables.each(function( i ) {
    let selector = $(this).data('toggle-id');
    $("#" + selector).hide();
  });
  
  $togglables.prepend('<i class="fa fa-caret-down toggle-caret"></i>');
  $(document).on("click", ".togglable", function(){
    $this = $(this);
    let selector = $this.data('toggle-id');
    $("#" + selector).toggle();
    let $caret = $this.children('.toggle-caret');
    if ($caret.hasClass('fa-caret-down')) {
      $caret.removeClass('fa-caret-down').addClass('fa-caret-up');
    }else{
      $caret.removeClass('fa-caret-up').addClass('fa-caret-down');
    }
  });

});
