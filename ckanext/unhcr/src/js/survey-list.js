$( document ).ready(function() {

  /*
  kobo-pkg-update-resources button starts a job to update all resources
  with new submissions
  */
  $(document).on("click", ".kobo-pkg-update-resources", function(){
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
						alert('Failed to start a job to update this survey ' + xhr.responseJSON.error);
					}
        }
      );

    }
  );

	$("#survey-list-table").fancyTable({
		sortColumn:2,
		pagination: true,
		inputPlaceholder: "Filter table...",
		perPage:10,
		globalSearch:true,
		inputStyle: "width: inherit"
	});

});
