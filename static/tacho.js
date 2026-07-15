       
// Nutzt html/canvas (https://www.w3schools.com/tags/ref_canvas.asp) für eine Messgeräte/Tacho/Gauge-Anzeige
// inspiriert durch Thomas Rose und seinen Kurs https://www.linkedin.com/learning/webtechniken-lernen-4-javascript

//var grasmax_gauge = {

export class GaugePara {
    constructor() {
        this.elmtname = "";
        this.title = "";
        this.min = 0;
        this.max = 0;
        this.redFrom = 0;
        this.redTo = 0;
        this.yellowFrom = 0;
        this.yellowTo = 0;
        this.yellowFrom2 = 0;
        this.yellowTo2 = 0;
        this.greenFrom = 0;
        this.greenTo = 0;
        this.akt = 0;
    }
}

function vCalcRadiation(min, max, akt) {
    try {
        if (akt < min) {
            akt = min;
        }
        var nGrad = (((akt-min) * 180) / (max - min)) - 180;
        return nGrad * Math.PI / 180;
    }
    catch (err) {
        document.getElementById('scripterr').innerHTML = 'Exception in vCalcRadiation(): '.concat( err);
    }
}

function vDrawArc(context, cr, radius, OffsetY, min, max, from, to) {
    try {
        context.beginPath();
        context.lineWidth = 10;
        context.strokeStyle = cr;
        //context.arc(0, OffsetY, radius - 10, Math.PI, Math.PI + Math.PI / 4);
        var nRotationFrom = vCalcRadiation(min, max, from);
        var nRotationTo = vCalcRadiation(min, max, to);
        context.arc(0, OffsetY, radius - 10, nRotationFrom, nRotationTo);
        context.stroke();
    }
    catch (err) {
        document.getElementById('scripterr').innerHTML = 'Exception in vDrawArc(): '.concat(err);
    }
}

export function vDrawGauge(p){
    try {

        elmt = p.elmtname;
        title = p.title;
        min = p.min;
        max = p.max;
        akt = p.akt;


        var canvas = document.getElementById(elmt);
        var context = canvas.getContext('2d');
        context.restore();
        context.resetTransform();

        var radius = (canvas.width / 2) - 1;

        var OffsetY = 0;
        var OffsetYTitle = 20;
        var OffsetYWert = 35;
        var OffsetYMinMax = 5;
        var MarginXMinMax = 7;

        context.translate(canvas.width / 2, canvas.height / 2);

        var nRotation = vCalcRadiation(min, max, akt);

        context.clearRect(-canvas.width / 2, -canvas.height / 2, canvas.width , canvas.height );


        vDrawArc(context, "rgba(16,150,24,0.5)", radius, OffsetY, min, max, p.greenFrom, p.greenTo);
        vDrawArc(context, "rgba(255,153,0.5)", radius, OffsetY, min, max, p.yellowFrom, p.yellowTo);
        if (p.yellowFrom2 > 0) {
            vDrawArc(context, "rgba(255,153,0.5)", radius, OffsetY, min, max, p.yellowFrom2, p.yellowTo2);
        }
        vDrawArc(context, "rgba(220,57,18,0.8)", radius, OffsetY, min, max, p.redFrom, p.redTo);


        // Zeiger
        context.beginPath();
        context.lineWidth = 3;
        context.fillStyle = "lightblue";
        context.strokeStyle = "rgba(70,132,238)";
        context.rotate(nRotation);
        context.moveTo(-20, -OffsetY);
        context.lineTo(canvas.width / 2 - 5, -OffsetY);
        context.stroke();
        context.rotate(-nRotation);

        //Zeigerpunkt
        context.beginPath();
        context.lineWidth = 1;
        context.strokeStyle = 'black';
        context.fillStyle = "rgba(70,132,238)";
        context.arc(0, OffsetY, 10, 0, 2 * Math.PI);
        context.fill();
        context.stroke();

        //Textfarbe
        context.fillStyle = "rgba(70,132,238)";

        //Titel
        context.beginPath()
        context.font = "16px Calibri";
        context.textAlign = "center";
        context.textBaseline = "top";
        context.fillText(title, 0, OffsetYTitle);

        //Wert
        context.beginPath()
        context.font = "20px Calibri";
        context.textAlign = "center";
        context.textBaseline = "top";
        context.fillText(akt, 0, OffsetYWert);

        //Von
        context.beginPath()
        context.font = "10px Calibri";
        context.textAlign = "left";
        context.textBaseline = "top";
        context.fillText(min, -canvas.width / 2 + MarginXMinMax, OffsetYMinMax);

        //bis
        context.beginPath()
        context.font = "10px Calibri";
        context.textAlign = "right";
        context.textBaseline = "top";
        context.fillText(max, canvas.width / 2 - MarginXMinMax, OffsetYMinMax);


    }
    catch (err) {
        document.getElementById('scripterr').innerHTML = 'Exception in vDrawGauge(): '.concat(err);
    }
}

export function vDrawGaugeText(divStatus, p, sText) {
    try {
        alert("asdsadwwwww");
        elmt = p.elmtname;

        var canvas = document.getElementById(elmt);
        var context = canvas.getContext('2d');
        context.restore();
        context.resetTransform();
        context.clearRect(0, 0, canvas.width, canvas.height);

        context.beginPath()
        context.fillStyle = "rgba(70,132,238)";
        context.font = "14px Calibri";
        context.textAlign = "left";
        context.textBaseline = "top";
        context.fillText(sText, 0, 0);
    }
    catch (err) {
        sErr = "";
        divStatus.innerHTML = 'Exception in vDrawGaugeInit(): '.concat(err);
    }
}



//};
