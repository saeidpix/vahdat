package ir.vahdat.app

import android.content.ContentValues
import android.graphics.Bitmap
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import java.io.ByteArrayOutputStream
import java.util.UUID

private val Navy = Color(0xFF061D71)
private val Blue = Color(0xFF0A49D3)
private val Red = Color(0xFFE10613)
private val Green = Color(0xFF098743)
private val Paper = Color(0xFFF3F6FD)
private val Ink = Color(0xFF15213A)

private enum class Page { HOME, NEW, QR, LIST, DETAIL, REPORT, SETTINGS }

class MainActivity: ComponentActivity() {
    private val scanText = mutableStateOf<String?>(null)
    private val scanner = registerForActivityResult(ScanContract()) { result ->
        if(result.contents != null) scanText.value = result.contents
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val store = CargoStore(this)
        setContent {
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
                MaterialTheme(
                    colorScheme = lightColorScheme(primary = Navy, secondary = Blue,
                        surface = Color.White, background = Paper, onSurface = Ink)
                ) {
                    VahdatApp(
                        store = store,
                        scanned = scanText.value,
                        scanHandled = { scanText.value = null },
                        startScan = {
                            scanner.launch(ScanOptions()
                                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                                .setPrompt("QR بارنامه را مقابل دوربین بگیرید")
                                .setBeepEnabled(false)
                                .setOrientationLocked(false))
                        },
                        saveQr = { saveQrToPhotos(it) }
                    )
                }
            }
        }
    }

    private fun saveQrToPhotos(bitmap: Bitmap) {
        if(Build.VERSION.SDK_INT < 29) {
            Toast.makeText(this,"برای ذخیره مستقیم تصویر، اندروید ۱۰ یا بالاتر لازم است.",Toast.LENGTH_LONG).show()
            return
        }
        try {
            val values = ContentValues().apply {
                put(MediaStore.Images.Media.DISPLAY_NAME,"vahdat-qr-" + System.currentTimeMillis() + ".png")
                put(MediaStore.Images.Media.MIME_TYPE,"image/png")
                put(MediaStore.Images.Media.RELATIVE_PATH,"Pictures/Vahdat")
            }
            val uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,values)
                ?: error("خطا در ذخیره فایل")
            contentResolver.openOutputStream(uri).use { output ->
                requireNotNull(output)
                bitmap.compress(Bitmap.CompressFormat.PNG,100,output)
            }
            Toast.makeText(this,"تصویر QR در گالری ذخیره شد.",Toast.LENGTH_LONG).show()
        } catch (e: Exception) {
            Toast.makeText(this,"ذخیره ناموفق: " + (e.message ?: ""),Toast.LENGTH_LONG).show()
        }
    }
}

@Composable
private fun VahdatApp(
    store: CargoStore,
    scanned: String?,
    scanHandled: () -> Unit,
    startScan: () -> Unit,
    saveQr: (Bitmap) -> Unit
) {
    var page by remember { mutableStateOf(Page.HOME) }
    var selectedId by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var revision by remember { mutableIntStateOf(0) }
    val bills = remember(revision) { store.all() }
    val selected = selectedId?.let { id -> bills.firstOrNull { it.id == id } }

    LaunchedEffect(scanned) {
        if(!scanned.isNullOrBlank()) {
            try {
                val (bill, fresh) = store.importQr(scanned)
                selectedId = bill.id
                revision++
                page = Page.DETAIL
                if(!fresh) error = "این بارنامه قبلاً ثبت شده؛ اطلاعات موجود نمایش داده می‌شود."
            } catch (e: Exception) {
                error = "QR قابل خواندن نیست: " + (e.message ?: "فرمت ناشناخته")
            }
            scanHandled()
        }
    }
    if(error!=null) AlertDialog(
        onDismissRequest={ error=null },
        title={ Text("پیام برنامه") },
        text={ Text(error ?: "") },
        confirmButton={ TextButton(onClick={error=null}) { Text("متوجه شدم") } }
    )
    Scaffold(
        containerColor = Paper,
        topBar = {
            Header(
                title = when(page) {
                    Page.HOME -> "اتوبنز وحدت"
                    Page.NEW -> "صدور بارنامه"
                    Page.QR -> "بارنامه صادر شد"
                    Page.LIST -> "بارنامه‌ها"
                    Page.DETAIL -> "جزئیات بارنامه"
                    Page.REPORT -> "گزارش مالی"
                    Page.SETTINGS -> "تنظیمات شعبه"
                },
                subtitle = if(page == Page.HOME) "مدیریت آفلاین بار و بارنامه" else null,
                back = if(page==Page.HOME) null else ({ page = Page.HOME })
            )
        },
        bottomBar = {
            NavigationBar(containerColor=Color.White) {
                listOf(
                    Triple(Page.HOME,"خانه",Icons.Outlined.Home),
                    Triple(Page.LIST,"بارنامه‌ها",Icons.Outlined.ReceiptLong),
                    Triple(Page.REPORT,"گزارش‌ها",Icons.Outlined.BarChart),
                    Triple(Page.SETTINGS,"تنظیمات",Icons.Outlined.Settings)
                ).forEach { (target,label,icon) ->
                    NavigationBarItem(
                        selected=page==target,
                        onClick={ page=target },
                        icon={ Icon(icon,contentDescription=label) },
                        label={Text(label,fontSize=10.sp)},
                        colors=NavigationBarItemDefaults.colors(selectedIconColor=Blue,
                            selectedTextColor=Navy,indicatorColor=Color(0xFFE5ECFF))
                    )
                }
            }
        }
    ) { insets ->
        Box(Modifier.fillMaxSize().padding(insets)) {
            when(page) {
                Page.HOME -> Home(
                    branch = store.branch, bills = bills,
                    goNew = {page=Page.NEW}, goScan=startScan,
                    goList={page=Page.LIST}, goReport={page=Page.REPORT}
                )
                Page.NEW -> NewWaybill(store.branch) { dest,sender,receiver,phone,pieces,total,prepaid ->
                    try {
                        val bill=store.newWaybill(dest,sender,receiver,phone,pieces,total,prepaid)
                        revision++; selectedId=bill.id; page=Page.QR
                    } catch(e: Exception) { error=e.message ?: "خطای ذخیره" }
                }
                Page.QR -> if(selected!=null) QrPage(
                    bill=selected,onSave=saveQr,onList={page=Page.LIST}
                )
                Page.LIST -> BillList(bills) { id -> selectedId=id;page=Page.DETAIL }
                Page.DETAIL -> if(selected!=null) BillDetail(
                    bill=selected,
                    onReceive={store.receive(selected.id);revision++},
                    onDeliver={person,paid->store.deliver(selected.id,person,paid);revision++},
                    onQr={page=Page.QR}
                )
                Page.REPORT -> Reports(bills)
                Page.SETTINGS -> SettingsPage(store.branch) {
                    store.branch=it;revision++;page=Page.HOME
                }
            }
        }
    }
}

@Composable
private fun Header(title:String,subtitle:String?=null,back:(()->Unit)?) {
    Row(
        modifier=Modifier.fillMaxWidth()
            .background(Brush.horizontalGradient(listOf(Navy,Color(0xFF123C9E))))
            .padding(horizontal=16.dp,vertical=12.dp),
        verticalAlignment=Alignment.CenterVertically
    ) {
        if(back!=null) IconButton(onClick=back) {
            Icon(Icons.Outlined.ArrowForward,contentDescription="بازگشت",tint=Color.White)
        }
        Image(
            painter=painterResource(R.drawable.brand_logo),contentDescription="نشان اتوبنز وحدت",
            modifier=Modifier.size(52.dp)
        )
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(title,color=Color.White,fontSize=19.sp,fontWeight=FontWeight.Bold)
            if(subtitle!=null) Text(subtitle,color=Color(0xFFDCE8FF),fontSize=11.sp)
        }
        if(back==null) Icon(Icons.Outlined.LocalShipping,contentDescription=null,
            tint=Color.White,modifier=Modifier.size(26.dp))
    }
}

@Composable
private fun Body(content:@Composable ColumnScope.()->Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement=Arrangement.spacedBy(12.dp),content=content
    )
}

@Composable
private fun Block(title:String?=null,content:@Composable ColumnScope.()->Unit) {
    Card(
        shape=RoundedCornerShape(16.dp),
        colors=CardDefaults.cardColors(containerColor=Color.White),
        elevation=CardDefaults.cardElevation(defaultElevation=2.dp),
        modifier=Modifier.fillMaxWidth()
    ) {
        Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
            if(title!=null) Text(title,color=Navy,fontWeight=FontWeight.Bold,fontSize=16.sp)
            content()
        }
    }
}

@Composable
private fun Info(label:String,value:String,tint:Color=Ink) {
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,
        verticalAlignment=Alignment.CenterVertically) {
        Text(label,color=Color(0xFF6F7891),fontSize=13.sp)
        Text(value,color=tint,fontWeight=FontWeight.SemiBold,fontSize=13.sp,
            textAlign=TextAlign.End)
    }
}
@Composable
private fun PrimaryButton(label:String,icon:ImageVector?=null,green:Boolean=false,onClick:()->Unit) {
    Button(
        onClick=onClick,modifier=Modifier.fillMaxWidth().height(52.dp),
        shape=RoundedCornerShape(12.dp),
        colors=ButtonDefaults.buttonColors(containerColor=if(green) Green else Blue)
    ) {
        if(icon!=null) {
            Icon(icon,contentDescription=null,modifier=Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(label,fontSize=16.sp,fontWeight=FontWeight.Bold)
    }
}
@Composable
private fun Field(label:String,value:String,onChange:(String)->Unit,
                  numeric:Boolean=false,placeholder:String="") {
    OutlinedTextField(
        value=value,onValueChange=onChange,modifier=Modifier.fillMaxWidth(),
        singleLine=true,label={Text(label)},placeholder={Text(placeholder)},
        keyboardOptions=KeyboardOptions(
            keyboardType=if(numeric) KeyboardType.Number else KeyboardType.Text),
        shape=RoundedCornerShape(12.dp)
    )
}

@Composable
private fun Home(branch:String,bills:List<Waybill>,goNew:()->Unit,goScan:()->Unit,
                 goList:()->Unit,goReport:()->Unit) {
    Body {
        Block {
            Info("شعبه فعال",branch)
            Info("تاریخ و ساعت",solarDate(System.currentTimeMillis()))
            Text("تمام عملیات بدون اینترنت انجام می‌شود.",
                fontSize=12.sp,color=Green)
        }
        Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
            HomeTile("صدور بارنامه","ثبت بار جدید",Icons.Outlined.NoteAdd,
                Color(0xFFE0EBFF),Modifier.weight(1f),goNew)
            HomeTile("دریافت بار","اسکن QR",Icons.Outlined.QrCodeScanner,
                Color(0xFFE0F8E9),Modifier.weight(1f),goScan)
        }
        Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
            HomeTile("بارنامه‌ها","جست‌وجو و تحویل",Icons.Outlined.ReceiptLong,
                Color.White,Modifier.weight(1f),goList)
            HomeTile("گزارش مالی","درآمد و مانده",Icons.Outlined.AccountBalanceWallet,
                Color.White,Modifier.weight(1f),goReport)
        }
        Block("خلاصه همین گوشی") {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                Count("صادرشده",bills.count{it.receivedAt==null && it.deliveredAt==null})
                Count("دریافت‌شده",bills.count{it.receivedAt!=null && it.deliveredAt==null})
                Count("تحویل‌شده",bills.count{it.deliveredAt!=null})
            }
        }
        Text("نسخه نمایشی ۰.۱ • داده‌های هر گوشی مستقل است.",
            color=Color.Gray,fontSize=11.sp)
    }
}
@Composable
private fun HomeTile(title:String,subtitle:String,icon:ImageVector,
                     color:Color,modifier:Modifier=Modifier,onClick:()->Unit) {
    Card(
        modifier=modifier.height(144.dp).clickable(onClick=onClick),
        shape=RoundedCornerShape(17.dp),
        colors=CardDefaults.cardColors(containerColor=color),
        elevation=CardDefaults.cardElevation(2.dp)
    ) {
        Column(Modifier.fillMaxSize().padding(12.dp),
            verticalArrangement=Arrangement.Center,
            horizontalAlignment=Alignment.CenterHorizontally) {
            Icon(icon,contentDescription=null,tint=Blue,modifier=Modifier.size(36.dp))
            Spacer(Modifier.height(10.dp))
            Text(title,fontWeight=FontWeight.Bold,color=Ink,fontSize=16.sp,textAlign=TextAlign.Center)
            Text(subtitle,color=Color.Gray,fontSize=11.sp,textAlign=TextAlign.Center)
        }
    }
}
@Composable
private fun Count(title:String,count:Int) {
    Column(horizontalAlignment=Alignment.CenterHorizontally) {
        Text(count.fa(),color=Blue,fontWeight=FontWeight.Bold,fontSize=23.sp)
        Text(title,fontSize=11.sp,color=Ink)
    }
}
@Composable
private fun NewWaybill(branch:String,
                      onCreate:(String,String,String,String,Int,Long,Long)->Unit) {
    var dest by remember { mutableStateOf("اصفهان") }
    var sender by remember { mutableStateOf("") }
    var receiver by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var count by remember { mutableStateOf("۱") }
    var total by remember { mutableStateOf("") }
    var prepaid by remember { mutableStateOf("") }
    Body {
        Block {
            Info("مبدأ (خودکار)",branch)
            Info("تاریخ و شماره بارنامه","ثبت خودکار")
            Field("شعبه مقصد",dest,{dest=it})
            Field("نام فرستنده",sender,{sender=it})
            Field("نام گیرنده",receiver,{receiver=it})
            Field("موبایل گیرنده (اختیاری)",phone,{phone=it})
            Field("تعداد بسته",count,{count=it},numeric=true)
        }
        Block("کرایه بارنامه • تومان") {
            Field("کل کرایه",total,{total=it},numeric=true,placeholder="مثلاً ۱۲۰۰۰۰۰")
            Field("پیش‌کرایه",prepaid,{prepaid=it},numeric=true,placeholder="مثلاً ۴۰۰۰۰۰")
            Surface(color=Color(0xFFE6F7EB),shape=RoundedCornerShape(10.dp)) {
                Row(Modifier.fillMaxWidth().padding(14.dp),
                    horizontalArrangement=Arrangement.SpaceBetween) {
                    Text("پس‌کرایه",fontWeight=FontWeight.Bold)
                    Text((total.amount()-prepaid.amount()).toman(),
                        color=Green,fontWeight=FontWeight.Bold)
                }
            }
        }
        PrimaryButton("صدور بارنامه و ساخت QR",Icons.Outlined.QrCode) {
            onCreate(dest,sender,receiver,phone,count.asciiDigits().toIntOrNull()?:1,
                total.amount(),prepaid.amount())
        }
        Text("فیلدها سخت‌گیرانه بررسی نمی‌شوند؛ برای پیش‌نمایش می‌توانید اطلاعات آزمایشی بزنید.",
            fontSize=11.sp,color=Color.Gray)
    }
}
@Composable
private fun QrPage(bill:Waybill,onSave:(Bitmap)->Unit,onList:()->Unit) {
    val qr = remember(bill.id) { qrBitmap(encodeQr(bill)) }
    Body {
        Block {
            Row(verticalAlignment=Alignment.CenterVertically) {
                Icon(Icons.Outlined.CheckCircle,contentDescription=null,tint=Green)
                Spacer(Modifier.width(8.dp))
                Text("بارنامه با موفقیت صادر شد",color=Green,fontWeight=FontWeight.Bold)
            }
            Info("شماره بارنامه",bill.id)
            Info("تاریخ صدور",solarDate(bill.createdAt))
            Info("مسیر",bill.origin + " ← " + bill.destination)
            Image(
                bitmap=qr.asImageBitmap(),contentDescription="QR بارنامه",
                modifier=Modifier.fillMaxWidth().height(280.dp)
            )
            Text("این QR را در گوشی مقصد اسکن کنید.",fontSize=13.sp,
                modifier=Modifier.fillMaxWidth(),textAlign=TextAlign.Center)
            PrimaryButton("ذخیره تصویر QR",Icons.Outlined.Save) {onSave(qr)}
        }
        PrimaryButton("بارنامه‌های من",Icons.Outlined.List) {onList()}
    }
}
@Composable
private fun BillList(bills:List<Waybill>,onOpen:(String)->Unit) {
    var q by remember { mutableStateOf("") }
    val items = bills.filter {
        q.isBlank() || (it.id + it.sender + it.receiver + it.phone + it.destination)
            .contains(q.trim(),ignoreCase=true)
    }
    Body {
        Field("جست‌وجو: شماره، نام یا موبایل",q,{q=it})
        if(items.isEmpty()) Block { Text("بارنامه‌ای پیدا نشد.") }
        items.forEach { b ->
            Card(
                modifier=Modifier.fillMaxWidth().clickable { onOpen(b.id) },
                shape=RoundedCornerShape(13.dp),
                colors=CardDefaults.cardColors(containerColor=Color.White)
            ) {
                Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(7.dp)) {
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                        Text(b.id,fontWeight=FontWeight.Bold,color=Navy,fontSize=12.sp)
                        Text(b.status,color=if(b.deliveredAt!=null) Green else Blue,fontSize=12.sp)
                    }
                    Text(b.origin + " ← " + b.destination,
                        fontWeight=FontWeight.SemiBold)
                    Info("گیرنده",b.receiver.ifBlank{"ثبت نشده"})
                    Info("کرایه کل",b.total.toman())
                    Text(solarDate(b.createdAt),fontSize=11.sp,color=Color.Gray)
                }
            }
        }
    }
}
@Composable
private fun BillDetail(bill:Waybill,onReceive:()->Unit,
                       onDeliver:(String,Long)->Unit,onQr:()->Unit) {
    var person by remember(bill.id) { mutableStateOf(bill.receiver) }
    var paid by remember(bill.id) { mutableStateOf(bill.due.coerceAtLeast(0L).toString()) }
    Body {
        Block("مشخصات بارنامه") {
            Info("شماره",bill.id)
            Info("وضعیت",bill.status,if(bill.deliveredAt!=null) Green else Blue)
            Info("مبدأ",bill.origin)
            Info("مقصد",bill.destination)
            Info("فرستنده",bill.sender)
            Info("گیرنده",bill.receiver)
            Info("موبایل",bill.phone)
            Info("تعداد بسته",bill.pieces.fa())
            Info("تاریخ صدور",solarDate(bill.createdAt))
            if(bill.receivedAt!=null) Info("دریافت در مقصد",solarDate(bill.receivedAt))
            if(bill.deliveredAt!=null) Info("تحویل به گیرنده",solarDate(bill.deliveredAt))
        }
        Block("حساب مالی") {
            Info("کل کرایه",bill.total.toman())
            Info("پیش‌کرایه",bill.prepaid.toman())
            Info("پس‌کرایه",bill.due.toman(),Blue)
            if(bill.deliveredAt!=null) Info("وصول در مقصد",bill.postCollected.toman(),Green)
        }
        if(bill.receivedAt == null) {
            PrimaryButton("ثبت دریافت بار",Icons.Outlined.Inventory2,true,onReceive)
        } else if(bill.deliveredAt == null) {
            Block("تحویل نهایی به گیرنده") {
                Field("نام تحویل‌گیرنده",person,{person=it})
                Field("پس‌کرایه وصول‌شده (تومان)",paid,{paid=it},numeric=true)
                PrimaryButton("ثبت تحویل و وصول کرایه",Icons.Outlined.Check,true) {
                    onDeliver(person,paid.amount())
                }
            }
        } else Block {
            Text("بار تحویل داده شد.",color=Green,fontWeight=FontWeight.Bold)
            Info("تحویل‌گیرنده",bill.deliveredTo)
        }
        PrimaryButton("نمایش QR بارنامه",Icons.Outlined.QrCode,onClick=onQr)
        if(!bill.originHere) Text("این بارنامه با QR وارد شده است؛ پیش‌کرایه آن درآمد صندوق این گوشی نیست.",
            color=Color.Gray,fontSize=11.sp)
    }
}
@Composable
private fun Reports(bills:List<Waybill>) {
    var filter by remember {mutableStateOf(0)}
    val now=java.time.Instant.ofEpochMilli(System.currentTimeMillis())
        .atZone(java.time.ZoneId.systemDefault())
    fun included(millis:Long?):Boolean {
        if(millis==null) return false
        if(filter==2) return true
        val d=java.time.Instant.ofEpochMilli(millis).atZone(java.time.ZoneId.systemDefault())
        return if(filter==0) d.toLocalDate()==now.toLocalDate()
        else solarYearMonth(millis)==solarYearMonth(System.currentTimeMillis())
    }
    val issued=bills.filter{it.originHere && included(it.createdAt)}
    val delivered=bills.filter{included(it.deliveredAt)}
    val received=bills.filter{included(it.receivedAt)}
    val sumIssued=issued.sumOf{it.total}
    val sumPre=issued.sumOf{it.prepaid}
    val sumPost=delivered.sumOf{it.postCollected}
    val receivable=bills.filter{ !it.originHere && it.deliveredAt==null }
        .sumOf{it.due.coerceAtLeast(0)}
    Body {
        Block("بازه گزارش") {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(4.dp)) {
                listOf("امروز","این ماه","همه").forEachIndexed { index,label ->
                    FilterChip(
                        selected=filter==index,onClick={filter=index},
                        label={Text(label,fontSize=12.sp)},
                        colors=FilterChipDefaults.filterChipColors(
                            selectedContainerColor=Color(0xFFE5EDFF)
                        )
                    )
                }
            }
            Info("تاریخ",solarDate(System.currentTimeMillis(),false))
        }
        ReportCard("کل کرایه بارنامه‌های صادرشده",sumIssued,Icons.Outlined.LocalShipping,Color(0xFFE2EEFF))
        ReportCard("پیش‌کرایه وصول‌شده در مبدأ",sumPre,Icons.Outlined.AccountBalanceWallet,Color(0xFFE5F5E9))
        ReportCard("پس‌کرایه وصول‌شده در مقصد",sumPost,Icons.Outlined.Payments,Color(0xFFECE6FF))
        ReportCard("مطالبات فعلی مقصد (همه تاریخ‌ها)",receivable,Icons.Outlined.Schedule,Color(0xFFFFE6EA))
        Block("تعداد عملیات این بازه") {
            Info("صدور بارنامه",issued.size.fa())
            Info("ثبت دریافت",received.size.fa())
            Info("ثبت تحویل",delivered.size.fa())
        }
        Text("گزارش فقط اطلاعات ثبت‌شده روی همین گوشی را شامل می‌شود. مبلغ‌های مبدأ و مقصد تکراری جمع نمی‌شوند.",
            fontSize=11.sp,color=Color.Gray)
    }
}
@Composable
private fun ReportCard(label:String,amount:Long,icon:ImageVector,color:Color) {
    Surface(color=color,shape=RoundedCornerShape(14.dp),modifier=Modifier.fillMaxWidth()) {
        Row(Modifier.padding(20.dp),verticalAlignment=Alignment.CenterVertically) {
            Icon(icon,contentDescription=null,tint=Navy,modifier=Modifier.size(30.dp))
            Spacer(Modifier.width(12.dp))
            Column {
                Text(label,fontSize=12.sp,color=Ink)
                Spacer(Modifier.height(4.dp))
                Text(amount.toman(),fontWeight=FontWeight.Bold,fontSize=21.sp,color=Navy)
            }
        }
    }
}
@Composable
private fun SettingsPage(branch:String,onSave:(String)->Unit) {
    var name by remember {mutableStateOf(branch)}
    Body {
        Block("نام شعبه این گوشی") {
            Field("شعبه",name,{name=it})
            PrimaryButton("ذخیره تنظیمات",Icons.Outlined.Save) {onSave(name)}
        }
        Block("درباره نسخه نمایشی") {
            Info("نام شرکت","اتوبنز وحدت")
            Info("نسخه","۰.۱ آفلاین")
            Text("برای نمایش روی دو گوشی، نام شعبه را در هر کدام جداگانه انتخاب کنید.",
                color=Ink,fontSize=13.sp)
            Text("QR این نسخه رمزگذاری نشده است؛ لطفاً برای آزمایش از اطلاعات ساختگی استفاده کنید.",
                color=Red,fontSize=12.sp)
        }
    }
}
