$( document ).ready(function() {

	$("#system-activities-list").fancyTable({
		pagination: true,
		inputPlaceholder: "Filter activities list table ...",
		perPage:20,
		globalSearch:true,
		inputStyle: "width: inherit"
	});

});
