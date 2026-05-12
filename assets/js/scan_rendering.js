// Shared scansion rendering module.
// Call ScansionRenderer.init(displayScheme, translateFn, explanationLang) before rendering.
// Call ScansionRenderer.render(el, v, opts) to build the gana-grid DOM into el.

var ScansionRenderer = (function() {

	var _displayScheme = 'IAST';
	var _translate = function(s) { return s; };
	var _explanationLang = 'sanskrit';

	var WEIGHT_PAIR_SLP = { 'gg': 'gaga', 'll': 'lala', 'gl': 'gala', 'lg': 'laga' };
	var INDIC_SCHEMES = ['DEV', 'BENGALI', 'GUJARATI'];

	function slpToDisplay(s) {
		if (!s || _displayScheme === 'SLP') return s;
		return _translate(s, 'SLP', _displayScheme);
	}

	function iastToDisplay(s) {
		if (!s || _displayScheme === 'IAST') return s;
		return _translate(s, 'IAST', _displayScheme);
	}

	function slpGanaToDisplay(s) {
		if (!s) return s;
		var slp = WEIGHT_PAIR_SLP[s] || (s.length === 1 ? s + 'a' : s);
		if (_displayScheme === 'SLP') return slp;
		return _translate(slp, 'SLP', _displayScheme);
	}

	function iastGanaToDisplay(s) {
		if (!s) return s;
		if (WEIGHT_PAIR_SLP[s]) return slpGanaToDisplay(s);
		if (_displayScheme === 'IAST') return s;
		return _translate(s, 'IAST', _displayScheme);
	}

	function alignGanaColumnsInScansion(scanEl) {
		var rows = Array.prototype.slice.call(scanEl.querySelectorAll('.pada-row'));
		if (rows.length < 2) return;
		rows.forEach(function(row) {
			Array.prototype.forEach.call(row.children, function(el) { el.style.minWidth = ''; });
		});
		var groups = {};
		rows.forEach(function(row) {
			var n = row.children.length;
			if (!groups[n]) groups[n] = [];
			groups[n].push(row);
		});
		Object.keys(groups).forEach(function(n) {
			var grp = groups[n];
			if (grp.length < 2) return;
			var maxWidths = [];
			grp.forEach(function(row) {
				Array.prototype.forEach.call(row.children, function(el, i) {
					var w = el.offsetWidth;
					if (maxWidths[i] === undefined || w > maxWidths[i]) maxWidths[i] = w;
				});
			});
			grp.forEach(function(row) {
				Array.prototype.forEach.call(row.children, function(el, i) {
					if (maxWidths[i] !== undefined) el.style.minWidth = maxWidths[i] + 'px';
				});
			});
		});
	}

	function getPadaDiagInfo(diag, padaIdx, numPadas) {
		var empty = { probSet: {}, ps: null, isLenError: false, imperfectLabel: null };
		if (!diag) return empty;

		if (diag.type === 'pada') {
			var padaKey = String(padaIdx + 1);
			var engLabel = diag.imperfect_label_english  && diag.imperfect_label_english[padaKey];
			var sktLabel = diag.imperfect_label_sanskrit && diag.imperfect_label_sanskrit[padaKey];
			var chosenLabel = _explanationLang === 'english' ? engLabel : sktLabel;
			var ps = diag.problem_syllables && diag.problem_syllables[padaKey];
			var lenError = engLabel === 'hypermetric' || engLabel === 'hypometric';
			var probSet = {};
			if (ps) ps.forEach(function(i) { probSet[i] = true; });
			var showLabel = false;
			if (chosenLabel) {
				var myPs = diag.problem_syllables && diag.problem_syllables[padaKey];
				var myHasBad = myPs && myPs.length > 0;
				if (myHasBad) {
					showLabel = true;
				} else {
					var labelSet = _explanationLang === 'english' ? diag.imperfect_label_english : diag.imperfect_label_sanskrit;
					var firstLabeledNoBad = null;
					for (var k = 1; k <= numPadas; k++) {
						if (labelSet && labelSet[String(k)]) {
							var kPs = diag.problem_syllables && diag.problem_syllables[String(k)];
							if (!kPs || kPs.length === 0) { firstLabeledNoBad = k; break; }
						}
					}
					showLabel = (firstLabeledNoBad === padaIdx + 1);
				}
			}
			return { probSet: probSet, ps: ps || null, isLenError: lenError, imperfectLabel: showLabel ? chosenLabel : null };
		}

		if (diag.type === 'half') {
			var halfKey    = (padaIdx <= 1) ? 'ab' : 'cd';
			var withinHalf = (padaIdx % 2 === 0) ? 'odd' : 'even';
			var d = diag[halfKey];
			if (!d) return empty;
			var engLabel2 = d.imperfect_label_english  && d.imperfect_label_english[withinHalf];
			var sktLabel2 = d.imperfect_label_sanskrit && d.imperfect_label_sanskrit[withinHalf];
			var chosenLabel2 = _explanationLang === 'english' ? engLabel2 : sktLabel2;
			var ps2 = d.problem_syllables && d.problem_syllables[withinHalf];
			var lenError2 = engLabel2 === 'hypermetric' || engLabel2 === 'hypometric';
			var probSet2 = {};
			if (!lenError2 && ps2) ps2.forEach(function(i) { probSet2[i] = true; });
			var hasOddProbs  = d.problem_syllables && d.problem_syllables['odd']  && d.problem_syllables['odd'].length  > 0;
			var hasEvenProbs = d.problem_syllables && d.problem_syllables['even'] && d.problem_syllables['even'].length > 0;
			var showLabel2 = false;
			if (chosenLabel2) {
				if      (hasOddProbs  && withinHalf === 'odd')  showLabel2 = true;
				else if (hasEvenProbs && withinHalf === 'even') showLabel2 = true;
				else if (!hasOddProbs && !hasEvenProbs)         showLabel2 = (withinHalf === 'even' || numPadas <= 2);
			}
			return { probSet: probSet2, ps: ps2 || null, isLenError: lenError2, imperfectLabel: showLabel2 ? chosenLabel2 : null };
		}

		return empty;
	}

	function render(el, v, opts) {
		var optWeights   = opts.weights;
		var optMorae     = opts.morae;
		var optGaRas     = opts.gaRas;
		var optAlignment = opts.alignment;

		var sylPadas  = (v.text_syllabified  || '').split('\n').map(function(p) { return p.trim(); });
		var wtPadas   = (v.syllable_weights   || '').split('\n').map(function(p) { return p.trim(); });
		var gaRaPadas = (v.gaRa_abbreviations || '').split('\n').map(function(p) { return p.trim(); });
		var morae     = v.morae_per_line || [];
		var diag      = v.diagnostic || null;

		var primaryLabel = v.meter_label ? v.meter_label.split(' atha vā ')[0] : '';
		var isUpajati  = primaryLabel.indexOf('upajāti') >= 0;
		var isJati     = !isUpajati && (
			primaryLabel.indexOf('jāti') >= 0 ||
			primaryLabel.indexOf('āryā') >= 0 ||
			primaryLabel.indexOf('gīti') >= 0 ||
			primaryLabel.indexOf('vaitālīya') >= 0 ||
			primaryLabel.indexOf('mātrā') >= 0
		);
		var isUnknownM = !v.meter_label || primaryLabel.indexOf('adhyavasitam') >= 0;
		var isAnustubh = primaryLabel.indexOf('anuṣṭubh') >= 0 ||
		                 primaryLabel.indexOf('anustubh') >= 0 ||
		                 primaryLabel.indexOf('ardham eva') >= 0;

		if (isAnustubh && v.meter_label && v.meter_label.indexOf('ardham eva') >= 0 && sylPadas.length === 4) {
			sylPadas  = [sylPadas[0]  + ' ' + sylPadas[1],  sylPadas[2]  + ' ' + sylPadas[3]];
			wtPadas   = [wtPadas[0]   + wtPadas[1],          wtPadas[2]   + wtPadas[3]];
			gaRaPadas = [gaRaPadas[0] + gaRaPadas[1],        gaRaPadas[2] + gaRaPadas[3]];
			morae     = morae.length >= 4 ? [morae[0] + morae[1], morae[2] + morae[3]] : morae;
		}

		var numPadas = Math.max(sylPadas.length, wtPadas.length);

		var GANA_FROM_WEIGHTS = {
			'lll': 'n', 'llg': 't', 'lgl': 'j', 'lgg': 'y',
			'gll': 'B', 'glg': 'r', 'ggl': 's', 'ggg': 'm'
		};
		function ganaNameFromWeights(wList, start) {
			var pat = '';
			for (var k = 0; k < 3; k++) pat += (wList[start + k] || '').toLowerCase();
			return GANA_FROM_WEIGHTS[pat] || '?';
		}

		var MATRA_GANA_SYLS = { 'ja': 3, 'kha': 4, 'bha': 3, 'sa': 3, 'ma': 3, 'ya': 3, 'ra': 3, 'ta': 3, 'na': 3 };
		function matraGanaSylCount(name) { return MATRA_GANA_SYLS[name] || name.length; }

		var imperfectLabels = [];
		var anyLabel = false;
		var padaDiagInfos = [];
		for (var p = 0; p < numPadas; p++) {
			var sylStr0 = sylPadas[p] || '';
			var wtStr0  = wtPadas[p]  || '';
			if (!sylStr0 && !wtStr0) { imperfectLabels.push(null); padaDiagInfos.push(null); continue; }
			var info0 = getPadaDiagInfo(diag, p, numPadas);
			padaDiagInfos.push(info0);
			imperfectLabels.push(info0.imperfectLabel);
			if (info0.imperfectLabel) anyLabel = true;
		}

		var scrollEl = document.createElement('div');
		scrollEl.className = 'scansion-scroll';
		var innerEl = document.createElement('div');
		innerEl.className = 'scansion-scroll-inner';
		scrollEl.appendChild(innerEl);
		el.appendChild(scrollEl);

		var labelColEl = null;
		if (anyLabel) {
			labelColEl = document.createElement('div');
			labelColEl.className = 'scansion-label-col';
			el.appendChild(labelColEl);
		}

		var rowWraps   = [];
		var labelSlots = [];

		for (var p = 0; p < numPadas; p++) {
			var sylStr   = sylPadas[p]  || '';
			var wtStr    = wtPadas[p]   || '';
			var gaRaStr  = gaRaPadas[p] || '';
			var moraeVal = morae[p];
			if (!sylStr && !wtStr) continue;

			var info    = padaDiagInfos[p] || { probSet: {}, ps: null, isLenError: false, imperfectLabel: null };
			var probSet = info.probSet;
			var ps      = info.ps;
			var lenError = info.isLenError;

			var sylList   = sylStr.split(' ').filter(function(s) { return s.length > 0; });
			var wtList    = wtStr.split('').filter(function(c)  { return 'lgLG'.indexOf(c) >= 0; });
			var ganaChars = gaRaStr ? gaRaStr.split('') : [];

			var hyperIdx = null;
			var gapIdx   = null;
			if (lenError && ps && ps.length === 1) {
				var pv = ps[0];
				if (pv >= 0) hyperIdx = pv;
				else         gapIdx   = (-pv) - 1;
			}
			if (gapIdx !== null) {
				sylList.splice(gapIdx, 0, '​');
				wtList.splice(gapIdx,  0, '');
			}

			var numSyls = Math.max(sylList.length, wtList.length);

			function makeSylBox(j) {
				var syl    = slpToDisplay(sylList[j] || '');
				var wt     = wtList[j]  || '';
				var isL    = wt.toUpperCase() === 'L';
				var isG    = wt.toUpperCase() === 'G';
				var isMissing = (sylList[j] === '​');
				var isProb = isMissing ? false
				           : lenError  ? (hyperIdx !== null && j === hyperIdx)
				           : !!(probSet && probSet[j]);
				var box = document.createElement('div');
				box.className = 'syl-box'
				              + (isMissing ? ' missing-syl' : '')
				              + (optWeights && !isMissing && isL ? ' L' : optWeights && !isMissing && isG ? ' G' : '')
				              + (isProb ? ' problem' : '');
				if (optWeights) {
					var sc = document.createElement('div'); sc.className = 'scan';
					sc.textContent = isL ? slpGanaToDisplay('l') : isG ? slpGanaToDisplay('g') : wt;
					box.appendChild(sc);
				}
				if (optAlignment) {
					var sy = document.createElement('div'); sy.className = 'syl';
					sy.textContent = syl;
					box.appendChild(sy);
				}
				return box;
			}

			function makeBareBox(j) {
				var wrap = document.createElement('div');
				wrap.className = 'gana-single';
				var boxWrap = document.createElement('div');
				boxWrap.className = 'gana-single-box';
				boxWrap.appendChild(makeSylBox(j));
				wrap.appendChild(boxWrap);
				var lbl = document.createElement('div');
				lbl.className = 'gana-label'; lbl.innerHTML = '&nbsp;';
				wrap.appendChild(lbl);
				return wrap;
			}

			function makeGanaGroup(gChar, startIdx) {
				var group = document.createElement('div');
				group.className = 'gana-group';
				var boxes = document.createElement('div');
				boxes.className = 'gana-group-boxes';
				for (var k = 0; k < 3 && startIdx + k < numSyls; k++) {
					boxes.appendChild(makeSylBox(startIdx + k));
				}
				group.appendChild(boxes);
				var lbl = document.createElement('div');
				lbl.className = 'gana-label';
				lbl.textContent = slpGanaToDisplay(gChar);
				group.appendChild(lbl);
				return group;
			}

			function makeMatraGanaGroup(name, startIdx, count) {
				if (count === 1) return makeBareBox(startIdx);
				var group = document.createElement('div');
				group.className = 'gana-group';
				var boxes = document.createElement('div');
				boxes.className = 'gana-group-boxes';
				for (var k = 0; k < count && startIdx + k < numSyls; k++) {
					boxes.appendChild(makeSylBox(startIdx + k));
				}
				group.appendChild(boxes);
				var lbl = document.createElement('div');
				lbl.className = 'gana-label';
				lbl.textContent = iastGanaToDisplay(name);
				group.appendChild(lbl);
				return group;
			}

			var row = document.createElement('div');
			row.className = 'pada-row' + (lenError ? ' length-error' : '');

			var matraGanaPadas = (v.mAtragaNa_abbreviations || '').split('\n').map(function(s) { return s.trim(); });
			var matraGanaNames = matraGanaPadas[p] ? matraGanaPadas[p].split(' ').filter(Boolean) : [];

			if (!optGaRas) {
				for (var j = 0; j < numSyls; j++) row.appendChild(makeSylBox(j));
			} else if (isJati && matraGanaNames.length > 0) {
				var sylIdx = 0;
				matraGanaNames.forEach(function(name) {
					var count = matraGanaSylCount(name);
					row.appendChild(makeMatraGanaGroup(name, sylIdx, count));
					sylIdx += count;
				});
				while (sylIdx < numSyls) { row.appendChild(makeBareBox(sylIdx++)); }
			} else if (isAnustubh && numSyls === 8 && ganaChars.length === 4) {
				var g1 = ganaNameFromWeights(wtList, 1);
				var g2 = ganaNameFromWeights(wtList, 4);
				row.appendChild(makeBareBox(0));
				row.appendChild(makeGanaGroup(g1, 1));
				row.appendChild(makeGanaGroup(g2, 4));
				row.appendChild(makeBareBox(7));
			} else {
				var effectiveGanas = ganaChars;
				if (effectiveGanas.length === 0 && numSyls >= 3) {
					effectiveGanas = [];
					for (var gi0 = 0; gi0 + 2 < numSyls; gi0 += 3) {
						effectiveGanas.push(ganaNameFromWeights(wtList, gi0));
					}
				}
				var triCount    = Math.floor(numSyls / 3);
				var numTriGanas = Math.min(triCount, effectiveGanas.length);
				var sylIdx = 0;
				for (var gi = 0; gi < numTriGanas; gi++) {
					row.appendChild(makeGanaGroup(effectiveGanas[gi], sylIdx));
					sylIdx += 3;
				}
				var singleChars = effectiveGanas.slice(numTriGanas);
				singleChars.forEach(function(gChar) {
					if (sylIdx >= numSyls) return;
					var wrap = document.createElement('div');
					wrap.className = 'gana-single';
					var boxWrap = document.createElement('div');
					boxWrap.className = 'gana-single-box';
					boxWrap.appendChild(makeSylBox(sylIdx++));
					wrap.appendChild(boxWrap);
					var lbl = document.createElement('div');
					lbl.className = 'gana-label';
					lbl.innerHTML = slpGanaToDisplay(gChar) || '&nbsp;';
					wrap.appendChild(lbl);
					row.appendChild(wrap);
				});
				while (sylIdx < numSyls) {
					var tw = document.createElement('div'); tw.className = 'gana-single';
					var tb = document.createElement('div'); tb.className = 'gana-single-box';
					tb.appendChild(makeSylBox(sylIdx++));
					tw.appendChild(tb);
					var tl = document.createElement('div'); tl.className = 'gana-label'; tl.innerHTML = '&nbsp;';
					tw.appendChild(tl);
					row.appendChild(tw);
				}
			}

			var wrap = document.createElement('div');
			wrap.className = 'pada-row-wrap';
			wrap.appendChild(row);
			if (optMorae && moraeVal !== undefined) {
				var mora = document.createElement('span');
				mora.className = 'pada-mora';
				mora.textContent = 'm: ' + moraeVal;
				wrap.appendChild(mora);
			}
			innerEl.appendChild(wrap);
			rowWraps.push(wrap);

			if (anyLabel) {
				var slot = document.createElement('div');
				slot.className = 'pada-label-slot';
				var labelText = imperfectLabels[p];
				if (labelText) {
					var ilbl = document.createElement('span');
					ilbl.className = 'pada-imperfect-label';
					ilbl.textContent = (_explanationLang === 'sanskrit') ? iastToDisplay(labelText) : labelText;
					slot.appendChild(ilbl);
				}
				labelColEl.appendChild(slot);
				labelSlots.push(slot);
			}
		}

		requestAnimationFrame(function() {
			if (!isJati) alignGanaColumnsInScansion(el);
			if (anyLabel && rowWraps.length === labelSlots.length) {
				for (var i = 0; i < rowWraps.length; i++) {
					labelSlots[i].style.minHeight = rowWraps[i].offsetHeight + 'px';
				}
			}
		});
	}

	return {
		init: function(displayScheme, translateFn, explanationLang) {
			_displayScheme   = displayScheme  || 'IAST';
			_translate       = translateFn    || function(s) { return s; };
			_explanationLang = explanationLang || 'sanskrit';
		},
		render: render,
		alignGanaColumnsInScansion: alignGanaColumnsInScansion,
	};

})();
