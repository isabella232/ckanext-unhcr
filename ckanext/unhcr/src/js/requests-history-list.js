$( document ).ready(function() {

	$("#requests-history-list").fancyTable({
		pagination: true,
		inputPlaceholder: "Filter requests history list table ...",
		perPage:20,
		globalSearch:true,
		inputStyle: "width: inherit"
	});

});
