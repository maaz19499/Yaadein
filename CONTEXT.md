# Yaadein

An AI-powered event photo and video sharing platform designed to collect, manage, and share event memories.

## Language

**User**:
A registered, authenticated account in the system (e.g., Host, Photographer, Admin) with login credentials.
_Avoid_: Client, Customer, Member

**Host**:
A User who creates and manages events, customizes branding, and moderates uploaded media.
_Avoid_: Organizer, Event Owner

**Guest**:
An unauthenticated visitor who accesses an event gallery via QR code or link, uploads media under their provided name, and views event content.
_Avoid_: Visitor, Anonymous User

**Photographer**:
A B2B User who uploads professional media, manages client galleries, and accesses premium features like white-labeling.
_Avoid_: Vendor, Creator

**Event**:
A scheduled gathering (e.g., a wedding or party) containing media uploaded by Guests, Hosts, and Photographers.
_Avoid_: Gallery

**Media**:
A photo or video uploaded to an Event.
_Avoid_: Image, File, Asset

**Album**:
A user-created subset of **Media** within an **Event**. Can be static (manually selected items) or dynamic (a query filtered by specific face clusters).
_Avoid_: Group, Collection, Tag

## Relationships

- An **Event** is created by one **Host** (who is a **User**)
- An **Event** contains **Media** uploaded by one or more **Guests** or the **Host**
- A **Guest** provides their name to access and upload **Media** to a specific **Event**
- An **Event** contains zero or more **Albums**
- An **Album** groups **Media** belonging to the same **Event**

## Example dialogue

> **Dev:** "When a **Guest** scans the QR code for an **Event**, do they need to sign in?"
> **Domain expert:** "No, they just provide their name to begin viewing the gallery and uploading **Media**."
> **Dev:** "And how do they find photos of themselves?"
> **Domain expert:** "They can select their own face cluster to view a dynamic **Album** of their photos."

## Flagged ambiguities

- **Guest Identity**: A Guest does not have credentials or a global account; their identity is established by the name they enter when accessing the event.
