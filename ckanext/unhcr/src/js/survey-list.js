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
