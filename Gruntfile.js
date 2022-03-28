module.exports = function(grunt) {

  // Project configuration.
  grunt.initConfig({
    pkg: grunt.file.readJSON('package.json'),

    postcss: {
      options: {
        processors: [
          require('postcss-import'),
          require('autoprefixer'),
          require('postcss-custom-media'),
          require('postcss-mixins'),
          require('postcss-custom-properties'),
          require('postcss-calc'),
          require('postcss-nesting'),
          require('postcss-color-function')
        ]
      },
      dist: {
        src: 'ckanext/unhcr/src/css/theme.css',
        dest: 'ckanext/unhcr/fanstatic/theme.css'
      }
    },

    concat: {
      options: {
        separator: '\n',
      },
      dist: {
        src: [
          'ckanext/unhcr/src/js/main.js',
          'ckanext/unhcr/src/js/curation.js',
          'ckanext/unhcr/src/js/hierarchy.js',
          'ckanext/unhcr/src/js/data-collector.js',
          'ckanext/unhcr/src/js/linked-datasets.js',
          'ckanext/unhcr/src/js/membership.js',
          'ckanext/unhcr/src/js/module-resource-type.js',
          'ckanext/unhcr/src/js/kobo-file-upload.js',
          'ckanext/unhcr/src/js/survey-list.js',
          'ckanext/unhcr/src/js/kobo-dataset.js',
          'ckanext/unhcr/src/js/plugins/fancyTable.min.js',  // from https://github.com/myspace-nu/jquery.fancyTable
          'ckanext/unhcr/src/js/geographies.js',
          'ckanext/unhcr/src/js/activities-list.js',
          'ckanext/unhcr/src/js/requests-history-list.js',
        ],
        dest: 'ckanext/unhcr/fanstatic/theme.js',
      },
    },

    watch: {
      css: {
        files: 'ckanext/unhcr/src/css/*.css',
        tasks: ['postcss']
      },
      js: {
        files: 'ckanext/unhcr/src/js/*.js',
        tasks: ['concat']
      }
    }

  });

  // Load the plugins
  grunt.loadNpmTasks('grunt-postcss');
  grunt.loadNpmTasks('grunt-contrib-concat');
  grunt.loadNpmTasks('grunt-contrib-watch');

  grunt.registerTask('default',['watch']);

};
