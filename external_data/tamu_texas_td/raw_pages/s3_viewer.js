
//var pages = [];
var continuationToken = null;
var items = [];
var bucket = null;
var prefix = null;
var limit = null; // items per page
var active_page = 1;

function navClick(target){
  var gotoPage = null;
  if (target == 'previous'){
	gotoPage = active_page - 1;
  } else if (target == 'next'){
	gotoPage = active_page + 1;
  } else {
	gotoPage = parseInt(document.getElementById('tb-s3objects_nr_'+target).children[0].innerHTML);
  }
  fetchItems(gotoPage);
}

async function initPage(){
  var usp = new URLSearchParams(window.location.search);
  bucket = usp.get('bucket');
  prefix = usp.get('prefix');
  limit = usp.get('limit');
  if (limit == null){
    limit = 50;
  } else {
    limit = parseInt(limit);
    if (![10, 25, 50, 100].includes(limit)){
      limit = 50;
    }
  }

  if (bucket == null){
    return;
  }

  //var breadcrumbs = [];

  if (prefix != null){
    if (prefix == '/'){
      prefix = '';
    }
  }
  /*var breadPrefix = prefix.replace(/\/+$/, '');
  if (breadPrefix.length){
    breadPrefix.split('/').forEach((element, index) => {
      breadcrumbs.push([element, encodeURIComponent(element + '/')]);
    });
  }*/

  fetchItems(1)
}

function getFormattedDate(dt){
  var yr = dt.getFullYear();
  var mo = dt.getMonth() + 1;
  var dy = dt.getDate();
  var hr = dt.getHours();
  var mt = dt.getMinutes();
  var sc = dt.getSeconds();
  return ''+yr+'-'+(mo < 10? '0'+mo: mo)+'-'+(dy < 10? '0'+dy: dy)+' '+(hr < 10? '0'+hr: hr)+':'+(mt < 10? '0'+mt: mt)+':'+(sc < 10? '0'+sc: sc);
}

function formatBytes(size){
  var units = ['B', 'kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
  var bytes = Math.max(size, 0);
  var pwr = Math.floor((bytes? Math.log(bytes): 0) / Math.log(1024));
  var unitsIdx = pwr;
  while (pwr > 0){
    if (pwr > 3){
      bytes /= (1 << 30);
      pwr -= 3
    } else {
      bytes /= (1 << (10 * pwr));
      break
    }
  }
  //return Math.round(bytes, 1) + ' ' + units[pwr];
  return bytes.toFixed(1) + ' ' + units[unitsIdx];
}

async function fetchItems(pageNr){
    if ((items.length > 0) && ((continuationToken == null) || (items.length >= (pageNr * limit)))){
      // don't need to fetch, just load
	  showResults(pageNr);
      return;
	}

	var params = new URLSearchParams({
      getXml: true,
      bucket: bucket
	});
    if (prefix != null){
      params.append('prefix', prefix);
    }
	if (continuationToken != null){
		params.append('continuationToken', continuationToken);
	}

	var subItems = [];
	try {
		var response = await fetch(`https://${window.location.host}${window.location.pathname}?${params}`, {
			method: 'GET',
			headers: {
				'Content-Type': 'application/x-www-form-urlencoded',
			}
		});
		if (!response.ok){
			throw new Error('Response status: '+response.status);
		}
		// const blob = await response.blob();
		var respText = await response.text();
		var xObj = new window.DOMParser().parseFromString(respText, 'text/xml');

		var aIsTruncated = xObj.getElementsByTagName('IsTruncated');
		var aCommonPrefixes = xObj.getElementsByTagName('CommonPrefixes');
		var aContents = xObj.getElementsByTagName('Contents');

  	    if ((aIsTruncated.length > 0) && (aIsTruncated[0].textContent == 'true')){
			continuationToken = xObj.getElementsByTagName('NextContinuationToken')[0].textContent;
		} else {
			continuationToken = null;
		}

	    // subdirs
        for (let elt of aCommonPrefixes){
          var dirPrefix = elt.getElementsByTagName('Prefix')[0].textContent;
          if (prefix == null){
            subItems.push({key: dirPrefix});
          } else {
            var lastElt = dirPrefix.substring(prefix.length);
            subItems.push({key: lastElt});
          }
        }

	    // files in this dir
        for (let elt of aContents){
		  var key = null;
          if (prefix == null){
            key = elt.getElementsByTagName('Key')[0].textContent;
          } else {
            key = elt.getElementsByTagName('Key')[0].textContent.substring(prefix.length);
          }
			var size = elt.getElementsByTagName('Size')[0].textContent;
  		    var lastModified = elt.getElementsByTagName('LastModified')[0].textContent;
            if (key.length > 0){// ListObjectsV2 occasionally returns 0 length ghost items, omit
			  subItems.push({
			    key: key,
			    size: size,
			    lastModified: lastModified
			  });
            }
		}
		subItems.sort((a, b) => a.key.localeCompare(b.key));
  	    items = items.concat(subItems);
        showResults(pageNr);
	} catch (error){
		console.error(error.message);
	}
}

async function showResults(pageNr){

    //var oddEven = true;
    var tBody = document.getElementById('tbody-s3objects');
    tBody.innerHTML = ''; // clear table
	// repopulate table
    var itemIdxStart = limit * (pageNr - 1);
    var itemIdxEnd = itemIdxStart + limit;
    items.slice(itemIdxStart, itemIdxEnd).forEach((elt, idx) => {

    var resRow = '<tr role="row"><td><a data-s3="object" href="';
      /*if (oddEven){
        resRow += 'odd';
      } else {
        resRow += 'even';
      }
      resRow +='"><td><a data-s3="object" href="';*/
      if ('size' in elt){ // file
        var timestamp = new Date(elt.lastModified);
        resRow += 'https://'+bucket+'.s3.amazonaws.com/';
        if (prefix != null){
          resRow += prefix;
        }
        resRow += encodeURIComponent(elt.key)+'">'+elt.key+'</a></td><td>'+getFormattedDate(timestamp)+'</td><td>'+formatBytes(elt.size)+'</td>';
      } else { // dir
        var dirPrefix = prefix;
        if ((dirPrefix == null)||(dirPrefix == '')){
          dirPrefix = elt.key;
        } else if (prefix.endsWith('/')){
          dirPrefix = prefix + elt.key;
        } else {
          dirPrefix = prefix + '/' + elt.key;
        }
        var dirParams = new URLSearchParams({
          bucket: bucket,
          prefix: dirPrefix,
          limit: limit
        });
        resRow += `${window.location.pathname}?${dirParams}`+'">'+elt.key+'</a></td><td></td><td></td>';
      }
      resRow += "</tr>\n";
      tBody.innerHTML += resRow;
      //oddEven != oddEven;
    });

	// set result count
    var objCount = ''+items.length;
    if (items.length > 999){
      objCount = '999+';
    }
    document.getElementById('tb-s3objects_info').innerHTML = 'Objects ('+objCount+')';

	var known_pages = 0;
	// clear and/or hide pagination buttons
	if (items.length == 0){ // there are no items in this bucket/prefix
		document.getElementById('tb-s3objects_paginate').style.display = 'none';
		return;
	}
	if (items.length <= limit){ // there's 1 page of items
		// hide pagination block
		document.getElementById('tb-s3objects_paginate').style.display = 'none';
		return;
	}

	// update pagination
	known_pages = Math.ceil(items.length / limit);
	active_page = pageNr; //Math.floor(offset / limit) + 1;
	var first_page = null;
	var last_page = null;
	var right_space = known_pages - active_page;
	if (known_pages > active_page + 1){
		first_page = Math.max((active_page - 2), 1);
		last_page = Math.min((first_page + 4), known_pages);
	} else { //known_pages == active_page or active_page + 1
		last_page = known_pages;
	  first_page = Math.max((last_page - 4), 1);
	}
	if (active_page == 1){
		// disable < button
		document.getElementById('tb-s3objects_previous').classList.add('disabled');
	} else {
		// enable < button
		document.getElementById('tb-s3objects_previous').classList.remove('disabled');
	}
	if (first_page > 1){
		// show pre ellipsis button
		document.getElementById('tb-s3objects_pre_ellipsis').style.display = 'inline';
	} else {
		// hide pre ellipsis button
		document.getElementById('tb-s3objects_pre_ellipsis').style.display = 'none';
	}
	let j=first_page;
	for (let i=1; i<6; i++){
		if (j <= last_page){
			var pageLi = document.getElementById('tb-s3objects_nr_'+i);
			// show number button, and set page number
			pageLi.children[0].innerHTML = ''+j;
			//pageLi.children[0].setAttribute('tb-s3objects_nr_'+i, j);
			pageLi.style.display = 'inline';
			if (j == active_page){
				// add active class to li
				pageLi.classList.add('active');
			} else {
				// remove active class from li
				pageLi.classList.remove('active');
			}
		} else {
			// hide page number button
			paegLi.style.display = 'none';
		}
		j++;
	}
	if ((last_page < known_pages) || (continuationToken != null)){
		// show post ellipsis button
		document.getElementById('tb-s3objects_post_ellipsis').style.display = 'inline';
	} else {
		// hide post ellipsis button
		document.getElementById('tb-s3objects_post_ellipsis').style.display = 'none';
	}
    if ((active_page < known_pages) || (continuationToken != null)){
		// enable > button
		document.getElementById('tb-s3objects_next').classList.remove('disabled');
	} else {
		// disable > button
		document.getElementById('tb-s3objects_next').classList.add('disabled');
	}
	// display pagination block
	document.getElementById('tb-s3objects_paginate').style.display = 'inline';
	document.getElementById('paginationRow').classList.remove('disabled');
}

$(window).on('load', function(){
  initPage();
});
