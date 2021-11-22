$( document ).ready(function() {

  function update_geography(div) {
    gobalid = div.text().trim();
    let url = '/api/action/geography_show?id=' + $this.text().trim();
      $.ajax({
        url: url,
        dataType: 'json',
        success: function(data) {
          div.html(data.result.name);
        }
    });
  }

  $(document).on('DOMNodeInserted', '#s2id_field-geographies .select2-choices .select2-search-choice', function () {
    $this = $(this);
    $div = $this.find('div');
    // changing html raises "DOMNodeInserted" again
    if (!$div.data('ready')) {
      update_geography($div);
    }
    $div.data('ready', true);
  });

});
