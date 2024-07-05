# Databricks notebook source
class Bronze():
    def __init__(self):
        self.base = '/FileStore/invoices'

    def getSchema(self):
        return """InvoiceNumber string, CreatedTime bigint, StoreID string, PosID string, CashierID string,
                CustomerType string, CustomerCardNo string, TotalAmount double, NumberOfItems bigint, 
                PaymentMethod string, TaxableAmount double, CGST double, SGST double, CESS double, 
                DeliveryType string,
                DeliveryAddress struct<AddressLine string, City string, ContactNumber string, PinCode string, 
                State string>,
                InvoiceLineItems array<struct<ItemCode string, ItemDescription string, 
                    ItemPrice double, ItemQty bigint, TotalValue double>>
            """

    def readInvoices(self):
        from pyspark.sql.functions import explode, split
        return (spark.readStream
            .format("json")
            .schema(self.getSchema())
            .option("cleanSource", "archive")
            .option("sourceArchiveDir", f"{self.base}/data/invoices_archive")
            .load(f"{self.base}/data")
                )
        
    def process(self):
        print(f"\nStarting Bronze Stream...", end='')
        invoicesDF = self.readInvoices()
        sQuery =  ( invoicesDF.writeStream
                            .queryName("bronze-ingestion")
                            .option("checkpointLocation", f"{self.base}/checkpoint/invoices_bz")
                            .outputMode("append")
                            .toTable("invoices_bz")           
                    ) 
        print("Done")
        return sQuery 
        

# COMMAND ----------

class Silver():
    def __init__(self):
        self.base = '/FileStore/invoices'

    def readInvoices(self):
        return ( spark.readStream
                    .table("invoices_bz")
                )
    
    def explodeInvoices(self, invoiceDF):
        return ( invoiceDF.selectExpr("InvoiceNumber", "CreatedTime", "StoreID", "PosID",
                                      "CustomerType", "PaymentMethod", "DeliveryType", "DeliveryAddress.City",
                                      "DeliveryAddress.State","DeliveryAddress.PinCode", 
                                      "explode(InvoiceLineItems) as LineItem")
                                    )  
           
    def flattenInvoices(self, explodedDF):
        from pyspark.sql.functions import expr
        return( explodedDF.withColumn("ItemCode", expr("LineItem.ItemCode"))
                        .withColumn("ItemDescription", expr("LineItem.ItemDescription"))
                        .withColumn("ItemPrice", expr("LineItem.ItemPrice"))
                        .withColumn("ItemQty", expr("LineItem.ItemQty"))
                        .withColumn("TotalValue", expr("LineItem.TotalValue"))
                        .drop("LineItem")
                )
        
    def appendInvoices(self, flattenedDF):
        return (flattenedDF.writeStream
                    .queryName("silver-processing")
                    .format("delta")
                    .option("checkpointLocation", f"{self.base}/checkpoint/invoice_line_items")
                    .outputMode("append")
                    .toTable("invoice_line_items")
        )

    def process(self):
           print(f"\nStarting Silver Stream...", end='')
           invoicesDF = self.readInvoices()
           explodedDF = self.explodeInvoices(invoicesDF)
           resultDF = self.flattenInvoices(explodedDF)
           sQuery = self.appendInvoices(resultDF)
           print("Done\n")
           return sQuery  
