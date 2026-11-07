package ir.vahdat.app

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.util.UUID

data class Waybill(
    val id: String, val origin: String, val destination: String,
    val sender: String, val receiver: String, val phone: String,
    val pieces: Int, val total: Long, val prepaid: Long, val createdAt: Long,
    val receivedAt: Long? = null, val deliveredAt: Long? = null,
    val deliveredTo: String = "", val postCollected: Long = 0L,
    val originHere: Boolean = true
) {
    val due: Long get() = total - prepaid
    val status: String get() = when {
        deliveredAt != null -> "تحویل‌شده"
        receivedAt != null -> "دریافت‌شده"
        else -> "صادرشده"
    }
}

class CargoStore(context: Context): SQLiteOpenHelper(context, "vahdat-demo.db", null, 1) {
    private val prefs = context.getSharedPreferences("vahdat-settings", Context.MODE_PRIVATE)
    var branch: String
        get() = prefs.getString("branch","تهران") ?: "تهران"
        set(value) { prefs.edit().putString("branch", value.ifBlank { "تهران" }).apply() }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("""
          CREATE TABLE waybills(
            id TEXT PRIMARY KEY, origin TEXT NOT NULL, destination TEXT NOT NULL,
            sender TEXT NOT NULL, receiver TEXT NOT NULL, phone TEXT NOT NULL,
            pieces INTEGER NOT NULL, total INTEGER NOT NULL, prepaid INTEGER NOT NULL,
            created_at INTEGER NOT NULL, received_at INTEGER, delivered_at INTEGER,
            delivered_to TEXT NOT NULL DEFAULT '', post_collected INTEGER NOT NULL DEFAULT 0,
            origin_here INTEGER NOT NULL
          )
        """.trimIndent())
        db.execSQL("CREATE INDEX idx_waybill_created ON waybills(created_at DESC)")
        db.execSQL("CREATE INDEX idx_waybill_phone ON waybills(phone)")
        db.execSQL("CREATE INDEX idx_waybill_receiver ON waybills(receiver)")
        db.execSQL("""
          CREATE TABLE events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            waybill_id TEXT NOT NULL, kind TEXT NOT NULL,
            amount INTEGER NOT NULL, happened_at INTEGER NOT NULL
          )
        """.trimIndent())
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}

    fun newWaybill(destination: String, sender: String, receiver: String,
                   phone: String, pieces: Int, total: Long, prepaid: Long): Waybill {
        val now = System.currentTimeMillis()
        val id = "VH-" + now + "-" + UUID.randomUUID().toString().take(6).uppercase()
        val bill = Waybill(id, branch, destination.ifBlank { "نامشخص" },
           sender, receiver, phone, pieces.coerceAtLeast(1), total, prepaid, now)
        check(insert(bill)) { "ثبت بارنامه انجام نشد" }
        event(id,"ISSUED",prepaid.coerceAtLeast(0),now)
        return bill
    }

    fun insert(b: Waybill): Boolean {
        val values = ContentValues().apply {
            put("id",b.id); put("origin",b.origin); put("destination",b.destination)
            put("sender",b.sender); put("receiver",b.receiver); put("phone",b.phone)
            put("pieces",b.pieces); put("total",b.total); put("prepaid",b.prepaid)
            put("created_at",b.createdAt); put("received_at",b.receivedAt)
            put("delivered_at",b.deliveredAt); put("delivered_to",b.deliveredTo)
            put("post_collected",b.postCollected); put("origin_here",if(b.originHere) 1 else 0)
        }
        return writableDatabase.insertWithOnConflict("waybills",null,values,
            SQLiteDatabase.CONFLICT_IGNORE) != -1L
    }

    fun importQr(raw: String): Pair<Waybill,Boolean> {
        val bill = decodeQr(raw)
        val fresh = insert(bill)
        if (fresh) event(bill.id,"IMPORTED",0L,System.currentTimeMillis())
        return Pair(find(bill.id) ?: bill, fresh)
    }

    fun receive(id: String): Boolean {
        val now = System.currentTimeMillis()
        val values = ContentValues().apply { put("received_at",now) }
        val n = writableDatabase.update("waybills",values,
            "id=? AND received_at IS NULL", arrayOf(id))
        if(n>0) event(id,"RECEIVED",0L,now)
        return n>0
    }

    fun deliver(id: String, person: String, paid: Long): Boolean {
        val now = System.currentTimeMillis()
        val values = ContentValues().apply {
            put("delivered_at",now); put("delivered_to",person)
            put("post_collected",paid)
        }
        val n = writableDatabase.update("waybills",values,
            "id=? AND received_at IS NOT NULL AND delivered_at IS NULL",arrayOf(id))
        if(n>0) event(id,"DELIVERED",paid,now)
        return n>0
    }

    private fun event(id: String, kind: String, amount: Long, time: Long) {
        writableDatabase.insert("events",null,ContentValues().apply {
            put("waybill_id",id);put("kind",kind);put("amount",amount);put("happened_at",time)
        })
    }

    fun find(id: String): Waybill? =
        readableDatabase.query("waybills",null,"id=?",arrayOf(id),null,null,null).use {
            if(it.moveToFirst()) it.readBill() else null
        }

    fun all(): List<Waybill> =
        readableDatabase.query("waybills",null,null,null,null,null,"created_at DESC").use {
            buildList { while(it.moveToNext()) add(it.readBill()) }
        }

    private fun Cursor.readBill(): Waybill = Waybill(
        id = getString(getColumnIndexOrThrow("id")),
        origin = getString(getColumnIndexOrThrow("origin")),
        destination = getString(getColumnIndexOrThrow("destination")),
        sender = getString(getColumnIndexOrThrow("sender")),
        receiver = getString(getColumnIndexOrThrow("receiver")),
        phone = getString(getColumnIndexOrThrow("phone")),
        pieces = getInt(getColumnIndexOrThrow("pieces")),
        total = getLong(getColumnIndexOrThrow("total")),
        prepaid = getLong(getColumnIndexOrThrow("prepaid")),
        createdAt = getLong(getColumnIndexOrThrow("created_at")),
        receivedAt = nullableLong("received_at"),
        deliveredAt = nullableLong("delivered_at"),
        deliveredTo = getString(getColumnIndexOrThrow("delivered_to")),
        postCollected = getLong(getColumnIndexOrThrow("post_collected")),
        originHere = getInt(getColumnIndexOrThrow("origin_here")) == 1
    )
    private fun Cursor.nullableLong(name: String): Long? =
        getColumnIndexOrThrow(name).let { if(isNull(it)) null else getLong(it) }
}
