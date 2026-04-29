# FileMaker Image Export Instructions

## Step 1: Create the export folder

Create this folder on your Desktop:
```
~/Desktop/fm_images/
```

## Step 2: Paste this script into FileMaker ScriptMaker

Open **Stuff.fmp12** in FileMaker, go to **Scripts > Script Workspace**, create a new script called **"Export All Images"**, and paste the steps below.

The script loops through each table and exports every container field as:
`<TableName>_<PrimaryKey>_<FieldName>.<ext>`

---

### FileMaker Script Steps

You'll need to create ONE script per table (or one big script with sections). Here's the logic for each table. In ScriptMaker, use these steps:

#### WATCHES
```
Go to Layout [ "Watch" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Watch::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Watch::Image Obv ) ]
    Export Field Contents [ Watch::Image Obv ; $folder & "Watch_" & $pk & "_ImageObv" ]
  End If
  If [ not IsEmpty( Watch::Image Rev ) ]
    Export Field Contents [ Watch::Image Rev ; $folder & "Watch_" & $pk & "_ImageRev" ]
  End If
  If [ not IsEmpty( Watch::Receipt ) ]
    Export Field Contents [ Watch::Receipt ; $folder & "Watch_" & $pk & "_Receipt" ]
  End If
  If [ not IsEmpty( Watch::Document ) ]
    Export Field Contents [ Watch::Document ; $folder & "Watch_" & $pk & "_Document" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### COINS
Go to Layout [ "Coin" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Coin::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Coin::Image 1 ) ]
    Export Field Contents [ Coin::Image 1 ; $folder & "Coin_" & $pk & "_Image1" ]
  End If
  If [ not IsEmpty( Coin::Image 2 ) ]
    Export Field Contents [ Coin::Image 2 ; $folder & "Coin_" & $pk & "_Image2" ]
  End If
  If [ not IsEmpty( Coin::Receipt ) ]
    Export Field Contents [ Coin::Receipt ; $folder & "Coin_" & $pk & "_Receipt" ]
  End If
  If [ not IsEmpty( Coin::Document 1 ) ]
    Export Field Contents [ Coin::Document 1 ; $folder & "Coin_" & $pk & "_Document1" ]
  End If
  If [ not IsEmpty( Coin::Document 2 ) ]
    Export Field Contents [ Coin::Document 2 ; $folder & "Coin_" & $pk & "_Document2" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### CAMERAS
Go to Layout [ "Camera" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Camera::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Camera::Image ) ]
    Export Field Contents [ Camera::Image ; $folder & "Camera_" & $pk & "_Image" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### LENSES
Go to Layout [ "Lens" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Lens::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Lens::Image ) ]
    Export Field Contents [ Lens::Image ; $folder & "Lens_" & $pk & "_Image" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### PENS
Go to Layout [ "Pen" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Pen::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Pen::Image ) ]
    Export Field Contents [ Pen::Image ; $folder & "Pen_" & $pk & "_Image" ]
  End If
  If [ not IsEmpty( Pen::Receipt ) ]
    Export Field Contents [ Pen::Receipt ; $folder & "Pen_" & $pk & "_Receipt" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### ART
Go to Layout [ "Art" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Art::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Art::Image ) ]
    Export Field Contents [ Art::Image ; $folder & "Art_" & $pk & "_Image" ]
  End If
  If [ not IsEmpty( Art::Receipt ) ]
    Export Field Contents [ Art::Receipt ; $folder & "Art_" & $pk & "_Receipt" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### VEHICLES
Go to Layout [ "Vehicle" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Vehicle::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Vehicle::Image ) ]
    Export Field Contents [ Vehicle::Image ; $folder & "Vehicle_" & $pk & "_Image" ]
  End If
  If [ not IsEmpty( Vehicle::Registration ) ]
    Export Field Contents [ Vehicle::Registration ; $folder & "Vehicle_" & $pk & "_Registration" ]
  End If
  If [ not IsEmpty( Vehicle::Insurance ) ]
    Export Field Contents [ Vehicle::Insurance ; $folder & "Vehicle_" & $pk & "_Insurance" ]
  End If
  If [ not IsEmpty( Vehicle::Invoice ) ]
    Export Field Contents [ Vehicle::Invoice ; $folder & "Vehicle_" & $pk & "_Invoice" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### RECORDINGS
Go to Layout [ "Recording" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Recording::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Recording::Image ) ]
    Export Field Contents [ Recording::Image ; $folder & "Recording_" & $pk & "_Image" ]
  End If
  If [ not IsEmpty( Recording::Receipt ) ]
    Export Field Contents [ Recording::Receipt ; $folder & "Recording_" & $pk & "_Receipt" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### RIFLES
Go to Layout [ "Rifle" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Rifle::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Rifle::Image ) ]
    Export Field Contents [ Rifle::Image ; $folder & "Rifle_" & $pk & "_Image" ]
  End If
  If [ not IsEmpty( Rifle::Receipt ) ]
    Export Field Contents [ Rifle::Receipt ; $folder & "Rifle_" & $pk & "_Receipt" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### CREDIT CARDS
Go to Layout [ "Credit Card" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Credit Card::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Credit Card::Image Front ) ]
    Export Field Contents [ Credit Card::Image Front ; $folder & "CreditCard_" & $pk & "_ImageFront" ]
  End If
  If [ not IsEmpty( Credit Card::Image Back ) ]
    Export Field Contents [ Credit Card::Image Back ; $folder & "CreditCard_" & $pk & "_ImageBack" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### PROPERTIES
Go to Layout [ "Property" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Property::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Property::Image ) ]
    Export Field Contents [ Property::Image ; $folder & "Property_" & $pk & "_Image" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop

#### PERSONS
Go to Layout [ "Person" ]
Go to Record/Request/Page [ First ]
Loop
  Set Variable [ $pk ; Value: Person::PrimaryKey ]
  Set Variable [ $folder ; Value: "file:" & Get(DesktopPath) & "fm_images/" ]
  If [ not IsEmpty( Person::Head Shot ) ]
    Export Field Contents [ Person::Head Shot ; $folder & "Person_" & $pk & "_HeadShot" ]
  End If
  If [ not IsEmpty( Person::Image 1 ) ]
    Export Field Contents [ Person::Image 1 ; $folder & "Person_" & $pk & "_Image1" ]
  End If
  If [ not IsEmpty( Person::Image 7 ) ]
    Export Field Contents [ Person::Image 7 ; $folder & "Person_" & $pk & "_Image7" ]
  End If
  If [ not IsEmpty( Person::Image 9 ) ]
    Export Field Contents [ Person::Image 9 ; $folder & "Person_" & $pk & "_Image9" ]
  End If
  If [ not IsEmpty( Person::License Obverse ) ]
    Export Field Contents [ Person::License Obverse ; $folder & "Person_" & $pk & "_LicenseObverse" ]
  End If
  If [ not IsEmpty( Person::License Reverse ) ]
    Export Field Contents [ Person::License Reverse ; $folder & "Person_" & $pk & "_LicenseReverse" ]
  End If
  If [ not IsEmpty( Person::Health Card Obv ) ]
    Export Field Contents [ Person::Health Card Obv ; $folder & "Person_" & $pk & "_HealthCardObv" ]
  End If
  If [ not IsEmpty( Person::Health Card Rev ) ]
    Export Field Contents [ Person::Health Card Rev ; $folder & "Person_" & $pk & "_HealthCardRev" ]
  End If
  If [ not IsEmpty( Person::Passport ) ]
    Export Field Contents [ Person::Passport ; $folder & "Person_" & $pk & "_Passport" ]
  End If
  If [ not IsEmpty( Person::Global Entry ) ]
    Export Field Contents [ Person::Global Entry ; $folder & "Person_" & $pk & "_GlobalEntry" ]
  End If
  If [ not IsEmpty( Person::Eye Prescription ) ]
    Export Field Contents [ Person::Eye Prescription ; $folder & "Person_" & $pk & "_EyePrescription" ]
  End If
  If [ not IsEmpty( Person::Medicare ) ]
    Export Field Contents [ Person::Medicare ; $folder & "Person_" & $pk & "_Medicare" ]
  End If
  Go to Record/Request/Page [ Next ; Exit after last: On ]
End Loop
```

## Step 3: Run the script

1. Open Stuff.fmp12 in FileMaker
2. Create the folder `~/Desktop/fm_images/`
3. Run the "Export All Images" script
4. Files will appear in `~/Desktop/fm_images/`

## Step 4: Run the Python import

Once the images are exported, run:
```bash
cd ~/Desktop/StuffApp
python3 import_fm_images.py ~/Desktop/fm_images/
```
