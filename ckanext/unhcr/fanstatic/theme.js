$( document ).ready(function() {

  // toggle account menu
  $( ".account-masthead .account" ).click(function() {
    $( this ).toggleClass( "active" );
  });

  // toggle login information
  $( ".login-splash .toggle a" ).click(function() {
    $( this ).parents(".info").toggleClass( "active" );
  });

});

// Validation
$(document).ready(function() {

  // Get fields
  var fields = $('.curation-validation ul[data-fields]').data('fields') || [];

  // Stop if no fields
  if (!fields.length) {
    return
  }

  // Highlight in form
  for (var field of fields) {
    var group = $(`[name="${field}"]`).closest('.control-group');
    group.addClass('curation-invalid');
    group.find('.controls').append(
      `<div class="info-block curation-info-block">
        <i class="fa fa-times"></i>
        This field need to be updated before the dataset can be published
      </div>`
    );
  }

});

// Header
$(document).ready(function() {
  var sidebar = $('.curation-data-deposit');
  if (sidebar.length) {
    var predicat = function() {return $(this).text() === "Data Deposit";}
    $('.navigation a').filter(predicat).parent().addClass('active');
  }
});

$( document ).ready(function() {

  // set default state
  //$(".hierarchy-tree").parent("li").addClass( "open" ); // open
  $(".hierarchy-tree").addClass('collapse').parent("li").addClass( "closed" ); // closed

  // add toggle button
  $( ".hierarchy-tree" ).prev().before(
    '<button class="hierarchy-toggle"><span>Expand / collapse<span></button>'
  );

  // let CSS know that this has happened
  $(".hierarchy-tree-top").addClass('has-toggle');

  // toggle on click
  $( ".hierarchy-toggle" ).click(function() {
    $( this ).siblings(".hierarchy-tree").collapse('toggle');
    $( this ).parent("li").toggleClass( "open closed" )
  });

  // auto expand parents of highlighted
  $(".hierarchy-tree-top .highlighted").parents(".closed").removeClass("closed").addClass("open").children(".hierarchy-tree").removeClass("collapse");
});

$( document ).ready(function() {

  // Activate select2 widget
  // We can't use programmatically generated
  // select html field because it requires select2@4.0
  $('#field-data_collector').select2({
    placeholder: 'Click to get a drop-down list or start typing a data collector title',
    width: '100%',
    multiple: true,
    tokenSeparators: [','],
    tags: [
      "United Nations High Commissioner for Refugees",
      "Action contre la faim",
      "Impact - REACH",
      "Agency for Technical Cooperation and Development",
      "CARE International",
      "Caritas",
      "Danish Refugee Council",
      "INTERSOS",
      "International Organization for Migration",
      "Mercy Corps",
      "Norwegian Refugee Council ",
      "Save the Children International",
      "MapAction",
      "CartONG",
      "iMMAP",
      "Office of the High Commissioner for Human Rights",
      "Food and Agriculture Organization",
      "United Nations Assistance Mission for Iraq",
      "United Nations Development Programme",
      "United Nations Educational, Scientific and Cultural Organization",
      "Union Nationale des Femmes de Djibouti",
      "United Nations Populations Fund",
      "UN-HABITAT",
      "United Nations Humanitarian Air Service",
      "United Nations Children's Fund",
      "United Nations Industrial Development Organization",
      "UNITAR/UNOSAT",
      "United Nations Mine Action Coordination Centre",
      "United Nations Mission in Liberia",
      "United Nations Mission in South Sudan",
      "United Nations Office for the Coordination of Humanitarian Affairs",
      "United Nations Office for Project Services",
      "UN Office for West Africa and the Sahel",
      "United Nations Relief and Works Agency ",
      "UN Security Council",
      "UNV",
      "UN Women",
      "World food Programme - Programme Alimentaire Mondial",
      "World Health Organization",
      "World Bank",
    ]
  });

});

$( document ).ready(function() {

  // Activate select2 widget
  $('#field-linked-datasets').select2({
    placeholder: 'Click to get a drop-down list or start typing a dataset title'
  });

});

$( document ).ready(function() {

  // Activate select2 widget
  $('#membership-username')
    .on('change', function(ev) {
      $(ev.target.form).submit();
    })
    .select2({
      placeholder: 'Click or start typing a user name',
    });

  // Activate select2 widget
  $('#membership-contnames')
    .on('change', function(ev) {
      toggleAddMembershipButton();
    })
    .select2({
      placeholder: 'Click or start typing a container name',
    });

  // Activate select2 widget
  $('#membership-role')
    .on('change', function(ev) {
      toggleAddMembershipButton();
    })
    .select2({
      placeholder: 'Click or start typing a role name',
    });

  function toggleAddMembershipButton() {
    if ($('#membership-contnames').val() && $('#membership-role').val()) {
      $('#membership-button').attr('disabled', false)
    } else {
      $('#membership-button').attr('disabled', true)
    }
  }

});

this.ckan.module('resource-type', function ($) {
  return {

    // Public

    options: {
      value: null,
    },

    initialize: function () {

      // Get main elements
      this.field = $('#field-resource-type')
      this.input = $('input', this.field)

      // Add event listeners
      $('button.btn-data', this.field).click(this._onDataButtonClick.bind(this))
      $('button.btn-attachment', this.field).click(this._onAttachmentButtonClick.bind(this))
      $('button:contains("Previous")').click(this._onPreviousButtonClick.bind(this))

      // Emit initialized
      this._onIntialized()

    },

    // Private

    _onIntialized: function () {
      if (this.options.value === 'data') {
        this._onDataButtonClick()
      } else if (this.options.value === 'attachment') {
        this._onAttachmentButtonClick()
      } else {
        this.field.nextAll().hide()
        this.field.show()
      }
    },

    _onDataButtonClick: function (ev) {
      if (ev) ev.preventDefault()
      this.field.hide()
      this.field.nextAll().show()
      // We allow to select only the "Microdata" option
      $('#field-file_type option').each(function () {
        if ($(this).val() !== 'microdata') {
          $(this).remove();
        }
      })
      this.input.val('data')
      this._fixUploadButton()
      this._hideLinkButton()
      this._appendUploadSizeInfoBlock()
    },

    _onAttachmentButtonClick: function (ev) {
      if (ev) ev.preventDefault()
      this.field.hide()
      this.field.nextAll().show()
      // We hide all the fields below "File Type"
      $('#field-file_type').parents('.form-group').nextAll('.form-group').hide()
      // We allow to select only NOT the "Microdata" option
      $('#field-file_type option').each(function () {
        if ($(this).val() === 'microdata') {
          $(this).remove();
        }
      })
      this.input.val('attachment')
      this._fixUploadButton()
      this._appendUploadSizeInfoBlock()
    },

    _onPreviousButtonClick: function (ev) {
      if (ev) ev.preventDefault()
      this._onIntialized()
    },

    _fixUploadButton: function () {
      // https://github.com/ckan/ckan/blob/master/ckan/public/base/javascript/modules/image-upload.js#L88
      // Ckan just uses an input field behind a button to mimic uploading after a click
      // Our resources setup breakes the width calcucations so we fix it here
      var input = $('#field-image-upload')
      input.css('width', input.next().outerWidth()).css('cursor', 'pointer')
    },

    _hideLinkButton: function() {
      $('.dataset-resource-form div.image-upload a:last-child').hide()
    },

    _appendUploadSizeInfoBlock: function() {
      $("#upload-size-info-block").insertAfter(
        $("#field-image-upload").siblings(":last")
      ).show()
    }

  };
});

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

/*!
 * jQuery fancyTable plugin v1.0.21
 * https://github.com/myspace-nu
 *
 * Copyright 2018 Johan Johansson
 * Released under the MIT license
 */

!function(i){i.fn.fancyTable=function(a){var r=i.extend({inputStyle:"",inputPlaceholder:"Search...",pagination:!1,paginationClass:"btn btn-light",paginationClassActive:"active",pagClosest:3,perPage:10,sortable:!0,searchable:!0,matchCase:!1,exactMatch:!1,onInit:function(){},onUpdate:function(){},testing:!1},a),l=this;return this.settings=r,this.tableUpdate=function(n){if(n.fancyTable.matches=0,i(n).find("tbody tr").each(function(){var a=0,e=!0,t=!1;i(this).find("td").each(function(){r.globalSearch||!n.fancyTable.searchArr[a]||l.isSearchMatch(i(this).html(),n.fancyTable.searchArr[a])?!r.globalSearch||n.fancyTable.search&&!l.isSearchMatch(i(this).html(),n.fancyTable.search)||Array.isArray(r.globalSearchExcludeColumns)&&r.globalSearchExcludeColumns.includes(a+1)||(t=!0):e=!1,a++}),r.globalSearch&&t||!r.globalSearch&&e?(n.fancyTable.matches++,!r.pagination||n.fancyTable.matches>n.fancyTable.perPage*(n.fancyTable.page-1)&&n.fancyTable.matches<=n.fancyTable.perPage*n.fancyTable.page?i(this).show():i(this).hide()):i(this).hide()}),n.fancyTable.pages=Math.ceil(n.fancyTable.matches/n.fancyTable.perPage),r.pagination){var a=n.fancyTable.paginationElement?i(n.fancyTable.paginationElement):i(n).find(".pag");a.empty();for(var e,t=1;t<=n.fancyTable.pages;t++)(1==t||t>n.fancyTable.page-(r.pagClosest+1)&&t<n.fancyTable.page+(r.pagClosest+1)||t==n.fancyTable.pages)&&(e=i("<a>",{html:t,"data-n":t,style:"margin:0.2em",class:r.paginationClass+" "+(t==n.fancyTable.page?r.paginationClassActive:"")}).css("cursor","pointer").bind("click",function(){n.fancyTable.page=i(this).data("n"),l.tableUpdate(n)}),t==n.fancyTable.pages&&n.fancyTable.page<n.fancyTable.pages-r.pagClosest-1&&a.append(i("<span>...</span>")),a.append(e),1==t&&n.fancyTable.page>r.pagClosest+2&&a.append(i("<span>...</span>")))}r.onUpdate.call(this,n)},this.isSearchMatch=function(a,e){r.matchCase||(a=a.toUpperCase(),e=e.toUpperCase());var t=r.exactMatch;return"auto"==t&&e.match(/^\".*?\"$/)?(t=!0,e=e.substring(1,e.length-1)):t=!1,t?a==e:new RegExp(e).test(a)},this.reinit=function(a){i(this).each(function(){i(this).find("th a").contents().unwrap(),i(this).find("tr.fancySearchRow").remove()}),i(this).fancyTable(this.settings)},this.tableSort=function(t){var a;void 0!==t.fancyTable.sortColumn&&t.fancyTable.sortColumn<t.fancyTable.nColumns&&(i(t).find("thead th div.sortArrow").each(function(){i(this).remove()}),(a=i("<div>",{class:"sortArrow"}).css({margin:"0.1em",display:"inline-block",width:0,height:0,"border-left":"0.4em solid transparent","border-right":"0.4em solid transparent"})).css(0<t.fancyTable.sortOrder?{"border-top":"0.4em solid #000"}:{"border-bottom":"0.4em solid #000"}),i(t).find("thead th a").eq(t.fancyTable.sortColumn).append(a),a=i(t).find("tbody tr").toArray().sort(function(a,e){a=i(a).find("td").eq(t.fancyTable.sortColumn),e=i(e).find("td").eq(t.fancyTable.sortColumn),a=i(a).data("sortvalue")?i(a).data("sortvalue"):a.html(),e=i(e).data("sortvalue")?i(e).data("sortvalue"):e.html();return"case-insensitive"==t.fancyTable.sortAs[t.fancyTable.sortColumn]&&(a=a.toLowerCase(),e=e.toLowerCase()),"numeric"==t.fancyTable.sortAs[t.fancyTable.sortColumn]?0<t.fancyTable.sortOrder?parseFloat(a)-parseFloat(e):parseFloat(e)-parseFloat(a):a<e?-t.fancyTable.sortOrder:e<a?t.fancyTable.sortOrder:0}),i(t).find("tbody").empty().append(a))},this.each(function(){if("TABLE"!==i(this).prop("tagName"))return console.warn("fancyTable: Element is not a table."),!0;var t,a,e,n,s=this;s.fancyTable={nColumns:i(s).find("td").first().parent().find("td").length,nRows:i(this).find("tbody tr").length,perPage:r.perPage,page:1,pages:0,matches:0,searchArr:[],search:"",sortColumn:r.sortColumn,sortOrder:void 0!==r.sortOrder&&(new RegExp("desc","i").test(r.sortOrder)||-1==r.sortOrder)?-1:1,sortAs:[],paginationElement:r.paginationElement},0==i(s).find("tbody").length&&(e=i(s).html(),i(s).empty(),i(s).append("<tbody>").append(i(e))),0==i(s).find("thead").length&&i(s).prepend(i("<thead>")),r.sortable&&(n=0,i(s).find("thead th").each(function(){s.fancyTable.sortAs.push("numeric"==i(this).data("sortas")?"numeric":"case-insensitive"==i(this).data("sortas")?"case-insensitive":null);var a=i(this).html(),a=i("<a>",{html:a,"data-n":n,class:""}).css("cursor","pointer").bind("click",function(){s.fancyTable.sortColumn==i(this).data("n")?s.fancyTable.sortOrder=-s.fancyTable.sortOrder:s.fancyTable.sortOrder=1,s.fancyTable.sortColumn=i(this).data("n"),l.tableSort(s),l.tableUpdate(s)});i(this).empty(),i(this).append(a),n++})),r.searchable&&(t=i("<tr>").addClass("fancySearchRow"),r.globalSearch?(a=i("<input>",{placeholder:r.inputPlaceholder,style:"width:100%;"+r.inputStyle}).bind("change paste keyup",function(){s.fancyTable.search=i(this).val(),s.fancyTable.page=1,l.tableUpdate(s)}),e=i("<th>",{style:"padding:2px;"}).attr("colspan",s.fancyTable.nColumns),i(a).appendTo(i(e)),i(e).appendTo(i(t))):(n=0,i(s).find("td").first().parent().find("td").each(function(){s.fancyTable.searchArr.push("");var a=i("<input>",{"data-n":n,placeholder:r.inputPlaceholder,style:"width:100%;"+r.inputStyle}).bind("change paste keyup",function(){s.fancyTable.searchArr[i(this).data("n")]=i(this).val(),s.fancyTable.page=1,l.tableUpdate(s)}),e=i("<th>",{style:"padding:2px;"});i(a).appendTo(i(e)),i(e).appendTo(i(t)),n++})),t.appendTo(i(s).find("thead"))),l.tableSort(s),r.pagination&&!r.paginationElement&&(i(s).find("tfoot").remove(),i(s).append(i("<tfoot><tr></tr></tfoot>")),i(s).find("tfoot tr").append(i("<td class='pag'></td>",{}).attr("colspan",s.fancyTable.nColumns))),l.tableUpdate(s),r.onInit.call(this,s)}),this}}(jQuery);