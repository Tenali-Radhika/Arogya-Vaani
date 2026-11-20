"""Generate data/doctors.json (FICTIONAL demo data)."""
import json, os
AREAS = {"Jayanagar":(12.9308,77.5838),"Koramangala":(12.9352,77.6245),"Whitefield":(12.9698,77.7500),
 "Malleshwaram":(13.0035,77.5647),"Indiranagar":(12.9784,77.6408),"HSR Layout":(12.9116,77.6389),
 "Rajajinagar":(12.9915,77.5520),"Yelahanka":(13.1007,77.5963)}
# name, specialty, area, languages, fee, pmjay, rating, schedule(start,end,days)
D = [
("Dr. Suresh Rao","orthopaedics","Jayanagar",["kn","hi","en"],600,True,4.7,("09:00","13:00",[0,1,2,3,4,5])),
("Dr. Meera Iyer","orthopaedics","Jayanagar",["en","ta","hi"],800,False,4.8,("16:00","20:00",[0,1,2,3,4])),
("Dr. Anand Gowda","orthopaedics","Koramangala",["kn","en"],700,True,4.5,("10:00","14:00",[0,2,4,5])),
("Dr. Farhan Sheikh","orthopaedics","Whitefield",["hi","en"],900,False,4.6,("10:00","16:00",[0,1,2,3,4])),
("Dr. Lakshmi Narayan","general physician","Jayanagar",["kn","hi","en"],400,True,4.6,("09:00","13:00",[0,1,2,3,4,5])),
("Dr. Ramesh Patil","general physician","Malleshwaram",["kn","hi","en"],350,True,4.4,("09:00","17:00",[0,1,2,3,4,5])),
("Dr. Sunita Verma","general physician","Whitefield",["hi","en"],500,True,4.5,("09:00","15:00",[0,1,2,3,4])),
("Dr. Kavya Shetty","general physician","HSR Layout",["kn","en","te"],450,False,4.7,("10:00","18:00",[0,1,2,3,4,5])),
("Dr. Prakash Hegde","cardiology","Jayanagar",["kn","en","hi"],1000,True,4.8,("10:00","13:00",[1,3,5])),
("Dr. Anitha Menon","cardiology","Indiranagar",["en","ml","hi"],1200,False,4.9,("14:00","18:00",[0,2,4])),
("Dr. Vikram Joshi","cardiology","Rajajinagar",["hi","kn","en"],900,True,4.5,("09:00","12:00",[0,1,2,3,4])),
("Dr. Shalini Reddy","gynaecology","Koramangala",["te","kn","en","hi"],800,False,4.7,("10:00","16:00",[0,1,2,3,4])),
("Dr. Pooja Kulkarni","gynaecology","Malleshwaram",["kn","hi","en"],600,True,4.6,("09:00","13:00",[0,1,2,3,4,5])),
("Dr. Rekha Nair","gynaecology","Whitefield",["ml","en","hi"],850,False,4.5,("11:00","17:00",[1,2,3,4,5])),
("Dr. Arjun Bhat","paediatrics","Jayanagar",["kn","en","hi"],500,True,4.8,("09:00","14:00",[0,1,2,3,4,5])),
("Dr. Divya Prabhu","paediatrics","HSR Layout",["kn","en"],600,False,4.6,("16:00","20:00",[0,1,2,3,4])),
("Dr. Imran Khan","paediatrics","Yelahanka",["hi","kn","en"],400,True,4.4,("09:00","15:00",[0,1,2,3,4,5])),
("Dr. Neha Agarwal","dermatology","Indiranagar",["hi","en"],900,False,4.7,("11:00","18:00",[0,1,2,3,4])),
("Dr. Girish Murthy","dermatology","Jayanagar",["kn","en","hi"],600,True,4.5,("10:00","14:00",[0,2,4,5])),
("Dr. Sandeep Kamath","ENT","Rajajinagar",["kn","hi","en"],550,True,4.6,("09:00","13:00",[0,1,2,3,4])),
("Dr. Tanvi Desai","ENT","Koramangala",["hi","en","kn"],750,False,4.7,("14:00","19:00",[0,1,2,3,4])),
("Dr. Mohan Raj","ophthalmology","Malleshwaram",["kn","ta","en"],500,True,4.8,("09:00","13:00",[0,1,2,3,4,5])),
("Dr. Priya Subramanian","ophthalmology","Indiranagar",["ta","en","hi"],800,False,4.6,("10:00","16:00",[1,2,3,4,5])),
("Dr. Harish Kini","diabetology","Yelahanka",["kn","en","hi"],500,True,4.5,("09:00","13:00",[0,1,2,3,4])),
("Dr. Fatima Begum","diabetology","Jayanagar",["hi","kn","en"],450,True,4.7,("15:00","19:00",[0,1,2,3,4,5])),
]
out=[]
for i,(n,s,a,l,f,p,r,(st,en,days)) in enumerate(D,1):
    lat,lng=AREAS[a]
    out.append({"id":f"doc{i:02d}","name":n,"specialty":s,"clinic":f"{n.split()[-1]} Clinic, {a}","area":a,
      "lat":round(lat+((i*7)%10-5)*0.0012,5),"lng":round(lng+((i*3)%10-5)*0.0012,5),
      "languages_spoken":l,"fee_inr":f,"pmjay_empanelled":p,"rating":r,
      "schedule":{"start":st,"end":en,"days":days,"slot_minutes":30}})
os.makedirs("data",exist_ok=True)
json.dump({"_note":"FICTIONAL DEMO DATA - not real doctors","doctors":out,"areas":{k:list(v) for k,v in AREAS.items()}},
          open("data/doctors.json","w",encoding="utf-8"),indent=1,ensure_ascii=False)
print(len(out),"doctors")
