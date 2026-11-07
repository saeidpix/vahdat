package ir.vahdat.app

import android.graphics.Bitmap
import android.graphics.Color
import android.util.Base64
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.MultiFormatWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.time.Instant
import java.time.ZoneId
import java.util.Locale
import java.util.zip.GZIPInputStream
import java.util.zip.GZIPOutputStream

fun String.asciiDigits(): String = buildString {
    this@asciiDigits.forEach { c ->
        append(when(c) {
            in '۰'..'۹' -> '0' + (c - '۰')
            in '٠'..'٩' -> '0' + (c - '٠')
            else -> c
        })
    }
}
fun String.amount(): Long = asciiDigits().filter { it in '0'..'9' }.toLongOrNull() ?: 0L
fun String.persianDigits(): String = map { if (it in '0'..'9') '۰' + (it - '0') else it }.joinToString("")
fun Long.toman(): String = String.format(Locale.US,"%,d",this).persianDigits() + " تومان"
fun Int.fa(): String = toString().persianDigits()

fun solarDate(millis: Long, withTime: Boolean = true): String {
    val local = Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault())
    val (year,month,day) = gregorianToJalali(local.year,local.monthValue,local.dayOfMonth)
    val date = String.format(Locale.US,"%04d/%02d/%02d",year,month,day)
    val time = String.format(Locale.US,"%02d:%02d:%02d",local.hour,local.minute,local.second)
    return (if(withTime) "$date - $time" else date).persianDigits()
}

// Gregorian -> solar Hijri (Jalali), arithmetic conversion.
private fun gregorianToJalali(gy: Int, gm: Int, gd: Int): Triple<Int,Int,Int> {
    val monthDays = intArrayOf(31,28,31,30,31,30,31,31,30,31,30,31)
    val gYear = gy - 1600
    val gMonth = gm - 1
    var days = 365*gYear + (gYear+3)/4 - (gYear+99)/100 + (gYear+399)/400
    for(i in 0 until gMonth) days += monthDays[i]
    if(gMonth>1 && ((gy%4==0 && gy%100!=0) || gy%400==0)) days++
    days += gd - 1
    var jDays = days - 79
    val cycles = jDays/12053
    jDays %= 12053
    var jy = 979 + 33*cycles + 4*(jDays/1461)
    jDays %= 1461
    if(jDays>=366) {
        jy += (jDays-1)/365
        jDays = (jDays-1)%365
    }
    return if(jDays<186) Triple(jy,1+jDays/31,1+jDays%31)
      else Triple(jy,7+(jDays-186)/30,1+(jDays-186)%30)
}

/** WARNING: Demo-only compression, not encryption or cryptographic signature.
  * Use fictitious customer data until the production security upgrade.
  */
fun encodeQr(b: Waybill): String {
    val j = JSONObject().apply {
        put("v",1);put("id",b.id);put("o",b.origin);put("d",b.destination)
        put("s",b.sender);put("r",b.receiver);put("p",b.phone)
        put("n",b.pieces);put("t",b.total);put("a",b.prepaid);put("c",b.createdAt)
    }
    val bytes = ByteArrayOutputStream()
    GZIPOutputStream(bytes).use { it.write(j.toString().toByteArray(Charsets.UTF_8)) }
    return "VHD1:" + Base64.encodeToString(bytes.toByteArray(),Base64.URL_SAFE or Base64.NO_WRAP)
}
fun decodeQr(data: String): Waybill {
    require(data.startsWith("VHD1:")) { "QR مربوط به اتوبنز وحدت نیست." }
    val binary = Base64.decode(data.removePrefix("VHD1:"),Base64.URL_SAFE or Base64.NO_WRAP)
    require(binary.size<16000) { "حجم QR نامعتبر است." }
    val plain = GZIPInputStream(ByteArrayInputStream(binary)).bufferedReader(Charsets.UTF_8).use {
        it.readText()
    }
    require(plain.length<25000) { "بارنامه بیش از حد بزرگ است." }
    val j = JSONObject(plain)
    require(j.getInt("v")==1) { "نسخه QR شناخته‌شده نیست." }
    val id = j.getString("id")
    require(id.startsWith("VH-") && id.length<90) { "شماره بارنامه نامعتبر است." }
    return Waybill(
        id=id,origin=j.optString("o"),destination=j.optString("d"),
        sender=j.optString("s"),receiver=j.optString("r"),phone=j.optString("p"),
        pieces=j.optInt("n",1).coerceAtLeast(1),total=j.optLong("t"),prepaid=j.optLong("a"),
        createdAt=j.getLong("c"),originHere=false
    )
}
fun qrBitmap(data: String, size: Int = 760): Bitmap {
    val hints = mapOf(EncodeHintType.MARGIN to 2,
        EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M,
        EncodeHintType.CHARACTER_SET to "UTF-8")
    val matrix = MultiFormatWriter().encode(data,BarcodeFormat.QR_CODE,size,size,hints)
    val bitmap = Bitmap.createBitmap(size,size,Bitmap.Config.ARGB_8888)
    for(y in 0 until size) for(x in 0 until size)
        bitmap.setPixel(x,y,if(matrix[x,y]) Color.BLACK else Color.WHITE)
    return bitmap
}
