$( document ).ready(function() {

	$("#survey-list-table").fancyTable({
		sortColumn:2,
		pagination: true,
		inputPlaceholder: "Filter table...",
		perPage:10,
		globalSearch:true,
		inputStyle: "width: inherit"
	});

});
