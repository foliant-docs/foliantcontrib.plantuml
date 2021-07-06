# First heading

Lorem ipsum dolor sit amet consectetur adipisicing, elit. Ratione non tempore fugit provident quibusdam recusandae aliquam odio dolorem architecto laudantium!

Correct diagram with plantuml tag:

<plantuml>
    @startuml

        a -> b

    @enduml
</plantuml>

Faulty diagram with plantuml tag:

<plantuml>

        a -a> b

    @enduml
</plantuml>

Correct raw diagram 

@startuml

    c -> d

    e <- f

@enduml

Another faulty diagram

<plantuml>
@startuml

    c -> d

    e <q- f

@endml
</plantuml>
